"""Predict one local X-ray using a saved FedProx checkpoint."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args()
    for path in (args.checkpoint, args.image):
        if not path.is_file():
            parser.error(f'File not found: {path}')

    print(json.dumps(predict_image(args.checkpoint, args.image, args.device), indent=2))

def predict_image(checkpoint_path, image_path, device='cpu'):
    import torch
    from PIL import Image
    from torchvision import transforms
    import fedprox_core as fl

    if device == 'cpu':
        torch.set_num_threads(2)
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA was requested but is unavailable.')
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    config = checkpoint['config']
    if config['architecture'] != 'resnet18' or config['class_mapping'] != {'NORMAL': 0, 'PNEUMONIA': 1}:
        raise ValueError('Unsupported checkpoint architecture or class mapping.')
    prep = config['preprocessing']
    transform = transforms.Compose([
        transforms.Resize(tuple(prep['image_size'])),
        transforms.ToTensor(),
        transforms.Normalize(prep['mean'], prep['std']),
    ])
    with Image.open(image_path) as source:
        # Match training: convert directly to RGB without orientation changes.
        tensor = transform(source.convert('RGB')).unsqueeze(0)
    model = fl.build_model(pretrained=False)
    model.load_state_dict(checkpoint['model_state_dict'], strict=True)
    model.to(device).eval()
    with torch.inference_mode():
        probabilities = torch.softmax(model(tensor.to(device)), dim=1)[0].cpu()
    prediction = int(probabilities.argmax().item())
    return {
        'predicted_class': ('NORMAL', 'PNEUMONIA')[prediction],
        'model_scores': {'NORMAL': float(probabilities[0]), 'PNEUMONIA': float(probabilities[1])},
        'selected_round': checkpoint['round'],
        'decision_rule': 'argmax; NORMAL wins ties, matching training evaluation',
        'notice': 'Research prototype. Scores are not calibrated clinical probabilities. Input must be a chest X-ray; this program cannot verify that.',
    }


if __name__ == '__main__':
    main()
