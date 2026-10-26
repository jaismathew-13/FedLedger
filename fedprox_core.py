"""ResNet-18 FedProx training primitives; sample-weighted model aggregation."""
import copy
import os
import random
import time
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from progress_display import ProgressBar



DATASET_PATH = r"D:\dataset_patientsplit"
TRAIN_DIR = os.path.join(DATASET_PATH, "train")
VAL_DIR = os.path.join(DATASET_PATH, "val")
TEST_DIR = os.path.join(DATASET_PATH, "test")

CLASS_FOLDERS = {"NORMAL": 0, "PNEUMONIA": 1}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

NUM_CLIENTS = 3
NUM_ROUNDS = 20
LOCAL_EPOCHS = 3
CLIENT_FRACTION = 1.0
CONVERGENCE_TARGET = 0.90

CLIENT_PROFILES = [
    {"name": "City_General_Hospital", "size_weight": 0.45, "prevalence_multiplier": 1.00},
    {"name": "Suburban_Community_Clinic", "size_weight": 0.25, "prevalence_multiplier": 0.50},
    {"name": "Respiratory_Referral_Center", "size_weight": 0.30, "prevalence_multiplier": 1.30},
]
PREVALENCE_NOISE_STD = 0.03
PREVALENCE_CLIP = (0.05, 0.65)

BATCH_SIZE = 32
LEARNING_RATE = 1e-4
NUM_WORKERS = 0
SEED = 42

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]



def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


train_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomRotation(10),
    transforms.ColorJitter(brightness=0.1, contrast=0.1),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])

eval_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])


def load_split_pairs(split_dir):
    if not os.path.isdir(split_dir):
        raise FileNotFoundError(f"Missing split folder: {split_dir}")
    subfolders = {
        n.lower(): n for n in os.listdir(split_dir)
        if os.path.isdir(os.path.join(split_dir, n))
    }
    pairs = []
    for class_name, label in CLASS_FOLDERS.items():
        actual = subfolders.get(class_name.lower())
        if actual is None:
            raise FileNotFoundError(f"Missing '{class_name}' folder inside {split_dir}")
        folder = os.path.join(split_dir, actual)
        files = sorted(
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        )
        pairs.extend((p, label) for p in files)
    counts = Counter(l for _, l in pairs)
    if counts.get(0, 0) == 0 or counts.get(1, 0) == 0:
        raise RuntimeError(f"Both classes must be present in {split_dir}")
    return pairs


class PneumoniaDataset(Dataset):
    def __init__(self, pairs, transform):
        self.pairs = pairs
        self.transform = transform

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, index):
        path, label = self.pairs[index]
        image = Image.open(path).convert("RGB")
        return self.transform(image), label


def compute_sizes(shares, total, min_images):
    shares = np.asarray(shares, dtype=float)
    shares = shares / shares.sum()
    sizes = np.floor(shares * total).astype(int)
    sizes[int(np.argmax(shares))] += total - int(sizes.sum())
    sizes = np.maximum(sizes, min_images)
    while sizes.sum() > total:
        sizes[int(np.argmax(sizes))] -= 1
    while sizes.sum() < total:
        sizes[int(np.argmax(shares))] += 1
    return sizes


def partition_realistic_hospitals(pairs, seed, profiles, min_images, noise_std, clip):
    rng = np.random.RandomState(seed)
    num_clients = len(profiles)

    normal_pool = [p for p in pairs if p[1] == 0]
    pneumonia_pool = [p for p in pairs if p[1] == 1]
    rng.shuffle(normal_pool)
    rng.shuffle(pneumonia_pool)

    total = len(pairs)
    global_prev = len(pneumonia_pool) / max(1, total)

    sizes = compute_sizes([p["size_weight"] for p in profiles], total, min_images)

    fracs = np.array([
        np.clip(global_prev * p["prevalence_multiplier"] + rng.normal(0.0, noise_std), clip[0], clip[1])
        for p in profiles
    ])

    want_p = np.round(sizes * fracs).astype(int)
    want_p = np.clip(want_p, 2, sizes - 2)

    if want_p.sum() > len(pneumonia_pool):
        scale = len(pneumonia_pool) / want_p.sum()
        want_p = np.maximum(np.floor(want_p * scale).astype(int), 2)
        while want_p.sum() > len(pneumonia_pool):
            want_p[int(np.argmax(want_p))] -= 1

    want_n = sizes - want_p
    if want_n.sum() > len(normal_pool):
        scale = len(normal_pool) / want_n.sum()
        want_n = np.maximum(np.floor(want_n * scale).astype(int), 2)
        while want_n.sum() > len(normal_pool):
            want_n[int(np.argmax(want_n))] -= 1
        want_p = sizes - want_n

    order = np.argsort(-want_p)
    client_pairs = [[] for _ in range(num_clients)]
    n_ptr = 0
    p_ptr = 0

    for c in order:
        s = int(sizes[c])
        avail_p = len(pneumonia_pool) - p_ptr
        avail_n = len(normal_pool) - n_ptr
        take_p = min(int(want_p[c]), avail_p)
        take_n = min(s - int(want_p[c]), avail_n)
        short = s - (take_p + take_n)
        if short > 0:
            extra_n = min(short, avail_n - take_n)
            take_n += extra_n
            short -= extra_n
            take_p += min(short, avail_p - take_p)
        client_pairs[c].extend(pneumonia_pool[p_ptr:p_ptr + take_p])
        p_ptr += take_p
        client_pairs[c].extend(normal_pool[n_ptr:n_ptr + take_n])
        n_ptr += take_n
        rng.shuffle(client_pairs[c])

    return client_pairs


def select_clients(num_clients, fraction, seed):
    rng = np.random.RandomState(seed)
    n = max(1, int(round(num_clients * fraction)))
    return sorted(int(c) for c in rng.choice(num_clients, size=n, replace=False))


def build_model(pretrained):
    if pretrained:
        model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    else:
        model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    return model


def class_weights_for(pairs, device):
    counts = Counter(l for _, l in pairs)
    n0 = max(1, counts.get(0, 0))
    n1 = max(1, counts.get(1, 0))
    total = n0 + n1
    return torch.tensor([total / (2 * n0), total / (2 * n1)], dtype=torch.float32, device=device)


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    criterion = nn.CrossEntropyLoss()
    total_loss = 0.0
    total = 0
    labels_all, preds_all, probs_all = [], [], []
    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        outputs = model(images)
        total_loss += criterion(outputs, labels).item() * images.size(0)
        total += labels.size(0)
        probs = torch.softmax(outputs, dim=1)[:, 1]
        labels_all.extend(labels.cpu().numpy().tolist())
        preds_all.extend(outputs.argmax(dim=1).cpu().numpy().tolist())
        probs_all.extend(probs.cpu().numpy().tolist())
    return (
        total_loss / max(1, total),
        np.asarray(labels_all),
        np.asarray(preds_all),
        np.asarray(probs_all),
    )


def compute_metrics(y_true, y_pred, probs):
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    sens = tp / (tp + fn) if tp + fn else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * prec * sens / (prec + sens) if prec + sens else 0.0
    try:
        auc = float(roc_auc_score(y_true, probs))
    except ValueError:
        auc = float("nan")
    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "accuracy": (tp + tn) / max(1, tp + tn + fp + fn),
        "balanced_accuracy": (sens + spec) / 2,
        "sensitivity": sens,
        "specificity": spec,
        "precision": prec,
        "f1": f1,
        "roc_auc": auc,
    }


def client_update(client_model, global_state, dataset, device, local_epochs, lr, class_weights, mu, label, progress_position=None, progress_callback=None):
    client_model.load_state_dict(global_state)
    client_model.to(device)
    client_model.train()

    global_params = [p.detach().clone() for p in client_model.parameters()]
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = optim.Adam(client_model.parameters(), lr=lr)

    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=torch.cuda.is_available(),
    )

    for epoch in range(local_epochs):
        bar = ProgressBar(loader, desc=f"{label} ep {epoch + 1}/{local_epochs}", unit="batch", leave=False, position=progress_position, dynamic_ncols=True, disable=progress_position == -1)
        for batch_number, (images, labels) in enumerate(bar, 1):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)
            loss = criterion(client_model(images), labels)

            if mu > 0:
                prox = torch.zeros((), device=device)
                for lp, gp in zip(client_model.parameters(), global_params):
                    prox = prox + (lp - gp).pow(2).sum()
                loss = loss + (mu / 2.0) * prox

            loss.backward()
            optimizer.step()
            bar.set_postfix(loss=f"{loss.item():.4f}")
            if progress_callback is not None:
                progress_callback(epoch + 1, local_epochs, batch_number, len(loader), loss.item())

    state = {k: v.detach().cpu().clone() for k, v in client_model.state_dict().items()}
    return state, len(dataset)


def sample_weighted_aggregate(client_states, client_sizes, progress_desc=None, progress_position=None):
    total = sum(client_sizes)
    weights = [s / total for s in client_sizes]
    avg = {}
    keys = client_states[0].keys()
    if progress_desc:
        keys = ProgressBar(keys, desc=progress_desc, unit="tensor", position=progress_position, leave=False, dynamic_ncols=True)
    for key in keys:
        stacked = torch.stack(
            [client_states[i][key].float() * weights[i] for i in range(len(client_states))],
            dim=0,
        )
        summed = stacked.sum(dim=0)
        dtype = client_states[0][key].dtype
        if dtype in (torch.int64, torch.int32, torch.int16):
            avg[key] = summed.round().to(dtype)
        else:
            avg[key] = summed.to(dtype)
    return avg


def run_federated(name, mu, init_state, client_datasets, client_weights, client_names,
                  val_loader, device, client_model, eval_model, on_round_end=None):
    set_seed(SEED)
    global_state = copy.deepcopy(init_state)

    history = []
    best_bal = -1.0
    best_round = 0
    best_state = None
    converged_round = None
    total_time = 0.0

    for rnd in range(NUM_ROUNDS):
        start = time.time()
        participating = select_clients(NUM_CLIENTS, CLIENT_FRACTION, seed=SEED + rnd)

        states, sizes = [], []
        for cid in ProgressBar(participating, desc=f"[{name}] round {rnd + 1}/{NUM_ROUNDS}", unit="client", leave=True):
            state, n = client_update(
                client_model, global_state, client_datasets[cid], device,
                LOCAL_EPOCHS, LEARNING_RATE, client_weights[cid], mu, client_names[cid],
            )
            states.append(state)
            sizes.append(n)

        global_state = sample_weighted_aggregate(states, sizes)
        round_time = time.time() - start
        total_time += round_time

        eval_model.load_state_dict(global_state)
        val_loss, y_true, y_pred, probs = evaluate(eval_model, val_loader, device)
        m = compute_metrics(y_true, y_pred, probs)

        history.append({
            "round": rnd + 1,
            "val_loss": val_loss,
            "val_accuracy": m["accuracy"],
            "val_balanced_accuracy": m["balanced_accuracy"],
            "val_sensitivity": m["sensitivity"],
            "val_specificity": m["specificity"],
            "val_precision": m["precision"],
            "val_f1": m["f1"],
            "val_roc_auc": m["roc_auc"],
            "round_time_sec": round_time,
        })

        print(
            f"[{name}] round {rnd + 1}/{NUM_ROUNDS} "
            f"val_loss {val_loss:.4f} acc {100 * m['accuracy']:.2f}% "
            f"bal_acc {100 * m['balanced_accuracy']:.2f}% f1 {100 * m['f1']:.2f}% "
            f"time {round_time:.1f}s"
        )

        if converged_round is None and m["balanced_accuracy"] >= CONVERGENCE_TARGET:
            converged_round = rnd + 1

        if m["balanced_accuracy"] > best_bal:
            best_bal = m["balanced_accuracy"]
            best_round = rnd + 1
            best_state = copy.deepcopy(global_state)

        if on_round_end is not None:
            on_round_end(history, global_state, best_state, best_round, best_bal)

    return {
        "name": name,
        "mu": mu,
        "history": history,
        "best_state": best_state,
        "best_round": best_round,
        "best_val_balanced_accuracy": best_bal,
        "converged_round": converged_round,
        "total_time_sec": total_time,
    }

