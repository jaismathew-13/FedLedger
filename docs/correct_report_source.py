"""Build the corrected report from the user-supplied LaTeX; no model execution."""
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(r'C:\Users\Shunz\.codex\attachments\3a5902bd-b74b-4a40-9f9f-c6f5500c9ccb\Pasted text.txt')
OUT = ROOT / 'docs' / 'report'
OUT.mkdir(exist_ok=True)
text = SOURCE.read_text(encoding='utf-8')
edits = []


def replace(old, new, why):
    global text
    if old not in text:
        raise ValueError('Replacement anchor missing: ' + old[:100])
    text = text.replace(old, new)
    edits.append(why)


replace(r'\usepackage{hyperref}', r'''\usepackage{microtype}
\usepackage{xurl}
\usepackage{hyperref}''', 'Add URL wrapping and typography support.')
replace(r'\newcolumntype{Y}{>{\raggedright\arraybackslash}X}', r'''\newcolumntype{Y}{>{\raggedright\arraybackslash}X}
\setlength{\emergencystretch}{2em}
% Supply the institution-approved logo beside this .tex file when available.
\newcommand{\institutionlogo}[1]{%
  \IfFileExists{MITS_LOGO.pdf}{\includegraphics[width=#1]{MITS_LOGO.pdf}}{%
    \fbox{\parbox[c][1.8cm][c]{#1}{\centering Institution logo\\(supply MITS\_LOGO.pdf)}}}}
% Institutional names, signatures, degree wording and dates require departmental confirmation.
% The original names are retained; conflicting coordinator names need author review.''', 'Make missing institution logo nonfatal; flag unverified institutional fields.')
replace(r'\includegraphics[width=0.38\textwidth]{MITS_LOGO.pdf}', r'\institutionlogo{0.38\textwidth}', 'Use guarded title-page logo.')
replace(r'\includegraphics[width=0.32\textwidth]{MITS_LOGO.pdf}', r'\institutionlogo{0.32\textwidth}', 'Use guarded certificate logo.')
replace('The project handoff records two distinct experiments.', 'The saved project evidence includes an earlier architecture experiment and multiple later portal campaigns.', 'Avoid claiming that only two experiments exist.')
replace('A later one-round dashboard smoke campaign completed the end-to-end workflow with three simulated hospitals.', 'Later one-round dashboard campaigns completed the end-to-end workflow with three simulated hospitals.', 'Update abstract to include later completed portal campaign.')
replace('Its reported pooled validation accuracy was 98.3013\\%, but subsequent image review identified', 'One documented smoke campaign reported pooled validation accuracy of 98.3013\\%, but subsequent image review identified', 'Bind abstract metric to the correct campaign.')
replace('A corrected staging version has not yet been registered or evaluated.', 'A reviewed staging copy exists, but the inspected evidence does not establish a completed evaluation of that corrected version.', 'Describe reviewed-v2 evidence boundary without assuming current registration state.')
replace('The two supplied base papers provide broad surveys, while the remaining eight papers provide system designs or medical-learning evaluations.', 'The two designated base papers provide broad surveys, while eight additional studies provide system designs or medical-learning evaluations. Foundational ResNet and FedProx references are also included.', 'Do not claim unprovided source PDFs were supplied; add foundational references.')
replace('Their search spans literature from 2018 to February 2025 and synthesizes more than one hundred papers across medical data sharing, connected medical devices, public-health applications, and telemedicine.', 'The review synthesizes medical blockchain--FL research and discusses medical data sharing, connected medical devices, public-health applications, and telemedicine.', 'Remove unnecessary detailed review counts/date claims.')
replace('Fung et al.', 'Shayan et al.', 'Correct Biscotti first-author attribution using the authors\' original paper.')
replace('fung2021biscotti', 'shayan2021biscotti', 'Match corrected Biscotti citation key throughout.')
replace('Biscotti: Peer-to-Peer Private and Secure Federated Learning', 'Biscotti: A Blockchain System for Private and Secure Federated Learning', 'Use the published Biscotti title.')
replace('They report that FedProx outperformed FedAvg across the reported metrics in their experimental setting.', 'Their study reports configuration-specific FedAvg/FedProx comparisons; its rankings cannot be transferred to this project.', 'Avoid an unnecessarily broad literature superiority claim.')
replace('using chest radiographs from 42 US and European hospitals \\cite{peng2023covid}.', 'using chest radiographs sourced from 42 US and European hospitals, organized into three federated clients \\cite{peng2023covid}.', 'Distinguish cohort hospitals from the three federated clients in Peng et al.')
replace('The source PDFs were supplied separately for reference. They are not reproduced in this report; attach them separately only if required by the department and permitted by the applicable publication terms.', 'Publisher or author links are provided in the bibliography. This verification received the LaTeX draft rather than the base-paper PDFs. Attach authorized source PDFs separately only if required by the department.', 'Remove unsupported claim that base-paper PDFs were supplied.')

start = text.index(r'\includegraphics[width=\textwidth,height=0.72\textheight,keepaspectratio]')
end = text.index('\n', start)
text = text[:start] + r'''\begin{tikzpicture}[
  box/.style={draw,rounded corners,align=center,text width=10.5cm,
              minimum height=0.8cm,font=\footnotesize},
  arr/.style={-{Latex[length=2mm]},thick},
  node distance=0.36cm
]
\node[box] (portal) {\textbf{FedLedger portals + MetaMask}\\
Admin: approve hospitals, freeze campaign, approve aggregation\\
Hospital: sign in, prepare client, authorize delegate, register data, opt in};
\node[box,below=of portal] (coordinator) {\textbf{Round coordinator, started in visible terminal}\\
Initial ResNet-18: ImageNet initialization and two-class head\\
Distribute the same incoming global checkpoint to three workers};
\node[box,below=of coordinator] (hospitals) {\textbf{Three simulated hospital workers on one laptop}\\
Own train/validation folders; local FedProx; save local \texttt{.pt} updates\\
Raw X-rays remain in local workspaces};
\node[box,below=of hospitals] (storage) {\textbf{Isolated local IPFS / Kubo}\\
Pin update checkpoints; obtain CIDs; verify SHA-256 digests};
\node[box,below=of storage] (review) {\textbf{Peer validation on each reviewer's own validation partition}\\
Both other hospitals must approve: BA $>0.5$ and BA $\geq$ baseline\\
Upload report JSON; rejected updates remain auditable and receive zero weight};
\node[box,below=of review] (aggregate) {\textbf{Admin approval, then off-chain aggregation}\\
Retrieve and verify accepted checkpoints; weight by samples $\times$ mean peer BA\\
All rejected: retain incoming global state};
\node[box,below=of aggregate] (global) {\textbf{Publish global checkpoint to IPFS and CID/digest to blockchain}\\
Evaluate pooled validation BA; first best round wins ties\\
Redistribute for next registered round, otherwise expose research inference};
\node[box,below=of global] (chain) {\textbf{Local Hardhat smart contracts and audit views}\\
HospitalDirectory: membership; ClientAuthorization: delegation\\
FederatedProtocolRegistry: updates, review commitments, global versions\\
Dashboards show workflow evidence; Blockscout independently indexes the live chain};
\foreach \a/\b in {portal/coordinator,coordinator/hospitals,hospitals/storage,
storage/review,review/aggregate,aggregate/global}
  \draw[arr] (\a.south) -- (\b.north);
\draw[arr,dashed] (global.south) -- (chain.north);
\end{tikzpicture}''' + text[end:]
edits.append('Replace missing architecture PNG with a self-contained TikZ architecture diagram.')

replace('The supplied project context does not record a fixed CPU, GPU model, RAM size, or benchmark hardware profile; these should be filled from the machine used for the final run rather than inferred.', 'The user-reported development laptop runs Windows and has a Ryzen 7 250 processor, an NVIDIA RTX 5060 GPU with 8 GB VRAM, and 24 GB RAM. These are operator-provided specifications, not a hardware profile independently captured for every historical run. CUDA-enabled PyTorch is used for local training when available; final reproducibility reporting should record the actual driver and package versions.', 'Correct hardware omission using the user-provided environment, labelled as such.')
replace('Hardhat and Solidity & Local Ethereum-compatible development chain and authorization/protocol contracts. \\\\', 'Hardhat 3 and Solidity & Local Ethereum-compatible development chain (chain ID 31337) and authorization/protocol contracts. \\\\\nMetaMask & Hospital wallet login and signed local-client delegation. \\\\\nBlockscout and Docker & Independent local chain explorer; separate from dashboard receipt views. \\\\', 'Include MetaMask and the implemented independent Blockscout explorer.')
replace('The system separates four concerns.', 'The system separates local learning, coordination, artifact storage, ledger commitments, and portal operations.', 'Correct inconsistent concern count.')
replace('Each hospital worker accesses only its registered local training and validation folders.', 'Each hospital worker is assigned its registered training and validation folders; peer workers evaluate candidates using their own validation data. This is application-level scoping, not operating-system isolation.', 'Clarify local-worker access is not a security isolation guarantee.')
replace('The server receives aggregate counts and configuration information rather than private image paths and manifests.', 'The browser-facing responses expose the owning hospital\'s setup and aggregate coordination information according to role. However, the local Python service scans image files, writes manifests containing absolute paths, hashes and patient mappings, and stores manifest references centrally on this laptop. The coordinator reads these manifests and dispatches local worker jobs. Raw image bytes are not uploaded to IPFS or blockchain, but the single-machine operator can access all hospital folders; the prototype does not yet provide remote institutional data isolation.', 'Fix false claim that server/coordinator never sees private paths or manifests.')
replace('A training lock prevents simultaneous coordinators from changing a campaign concurrently.', 'A process-level training lock prevents overlapping training executions on this local system; it is not a distributed multi-server locking protocol.', 'Describe the actual local training lock boundary.')
replace('The owner wallet\'s private key is not exported.', 'The owner wallet\'s private key is not exported by the portal; the delegated development client has a locally stored signing key.', 'Distinguish MetaMask owner key from the local delegated signing key.')
replace('The registered configuration described in the handoff uses three hospitals, three local epochs, FedProx $\\mu=0.01$, and seed 42.', 'The registered configuration uses exactly three hospitals, three local epochs, FedProx $\\mu=0.01$, and seed 42. Campaigns declare a round count within the approved maximum; completed one-round smoke campaigns must not be described as twenty-round campaigns.', 'Separate approved maximum round count from campaign round count.')
replace('The local optimizer is Adam with class-weighted cross-entropy and a FedProx penalty.', 'The initial global model is an ImageNet-initialized ResNet-18 with its final layer replaced by a two-class head \\cite{he2016resnet}. Portal campaigns retrieve the preserved initial checkpoint, rather than starting from the previously selected pneumonia checkpoint. Images are converted to RGB and resized to $224\\times224$. Training uses random rotation up to $10^{\\circ}$ and brightness/contrast jitter of 0.1; evaluation omits these random augmentations. Both use ImageNet normalization. The local optimizer is Adam with learning rate $10^{-4}$, batch size 32, class-weighted cross-entropy and a FedProx penalty \\cite{li2020fedprox}.', 'Document actual initialization, preprocessing and optimizer from code.')
replace('Rejected updates receive zero weight. If $\\mathcal{A}$ is empty, the incoming global model is retained.', 'Rejected updates receive zero weight. Floating-point state tensors use the weighted average; integer buffers use the existing weighted-average-then-round convention. If $\\mathcal{A}$ is empty, the incoming global model is retained. The weights are derived from validation scores, so these validation sets participate in model development rather than serving as independent final tests.', 'Clarify integer buffers and validation reuse in weighting.')
replace('SQLite stores application and coordination state needed by the portals.', 'SQLite stores application and coordination state needed by the portals. Specifically, \\texttt{HospitalDirectory} tracks membership, \\texttt{ClientAuthorization} tracks delegated consent, and \\texttt{FederatedProtocolRegistry} tracks protocol records. Update/global CIDs and digests are committed on-chain. Peer-review transactions commit report evidence hashes and decision data; peer-report CIDs are retained in off-chain artifacts rather than directly in those review transactions. Rejected checkpoints are not deleted from IPFS merely because their aggregation weight is zero.', 'Distinguish report hashes from report CIDs and preserve rejected artifact audit semantics.')
replace('A real deployment would require institutional identity verification, secret and network isolation, persistent infrastructure, privacy/security review, and governance agreements.', 'A real deployment would require institutional identity verification, remote hospital agents and authenticated transport, secret and network isolation, persistent infrastructure, privacy/security review, and governance agreements. Hardhat development state is normally ephemeral when its node is stopped; a replacement chain cannot be represented as the original chain. Saved receipts remain historical evidence, and live verification requires the matching chain instance. Blockscout indexes that live development chain independently but does not make it persistent or clinically trustworthy.', 'Add local chain lifecycle and independent explorer limitations.')
replace('The project handoff separates the earlier architecture experiment from a later dashboard-driven smoke campaign.', 'The evidence distinguishes an earlier architecture experiment from later dashboard-driven campaigns. The cases below are identified by run or campaign ID and are not an exhaustive claim that only two runs exist.', 'Update results scope to acknowledge multiple campaigns.')
replace('The mechanical consistency of peer decisions, aggregation weights, tensors, checkpoint hash, and then-live transaction receipts was independently checked.', 'A saved verification script checked the mechanical consistency of peer decisions, aggregation weights, tensors, checkpoint hash, and then-live transaction receipts. This is a project-local consistency check, not an external audit or independent clinical validation.', 'Remove ambiguous independent-audit claim.')
replace('the smoke campaign found a probable related radiograph pair', 'campaign \\texttt{34c72e51} found a probable related radiograph pair', 'Tie leakage finding to the reviewed campaign.')
replace('it has not yet been registered or evaluated.', 'no completed evaluation of that reviewed version is established by the inspected evidence.', 'Avoid making unsupported live registration-state claim.')
replace('These are image counts, not unique-patient counts.', 'These are image counts, not unique-patient counts. The staging names \\texttt{hospital1}--\\texttt{hospital3} are folder labels, not permanent dashboard hospital identities; the actual campaign mapping must be read from its frozen registration and manifests.', 'Prevent staging folder labels being confused with later portal hospital mappings.')
replace('Literature review and scope definition & Completed for this report draft & Ten supplied papers summarized and cited.', 'Literature review and scope definition & Draft prepared & Ten related studies plus foundational method papers cited; departmental review remains required.', 'Avoid falsely certifying literature review complete or PDFs supplied.')
replace('Renew approvals and client delegation & Pending after chain replacement & Reapprove selected participants and reauthorize their local clients.', 'Check approvals and client delegation & Conditional & After chain replacement, reapprove and reauthorize affected clients; inspect live state before declaring this pending.', 'Make operational status conditional, not a stale live-state assertion.')
replace('The next steps are to renew hospital approvals and delegated clients after the chain replacement, register the corrected data as a new immutable version, pre-register a longer experiment with repeated seeds, and evaluate a frozen model on a genuinely independent patient-wise test cohort.', 'The next steps are to check live approvals and delegated-client authorization after any chain replacement, register and audit the reviewed data as a new immutable version where needed, pre-register a longer experiment with repeated seeds, and evaluate a frozen model on a genuinely independent patient-wise test cohort.', 'Make conclusion consistent with verified evidence and conditional operational state.')
replace('The two base papers used to frame the literature review are:', 'The two designated base references used to frame the literature review are:', 'Distinguish named references from unseen attachments.')

# Every added project-result number below is read from preserved multiseed_outputs.
later = ROOT / 'multiseed_outputs/portal_campaigns/dbcb01f4-e574-4027-8f54-d9772d08c8d2'
status = json.loads((later/'status.json').read_text())
history = json.loads((later/'history.json').read_text())
assert status['state'] == 'completed' and len(history) == 1
v = history[0]['validation']
later_section = r'''\section{Later Completed Portal Campaign}
The preserved record for campaign \url{dbcb01f4-e574-4027-8f54-d9772d08c8d2}
also reports a completed one-round campaign with seed 42, three local epochs,
and $\mu=0.01$. It used registered code-based hospital workspaces and accepted
all three updates. It is a distinct workflow execution, not an additional seed
or an independent external test. Its saved pooled validation values are:
\begin{table}[htbp]
\centering
\caption{Saved validation results for the later one-round portal campaign}
\begin{tabular}{lr}
\toprule
\textbf{Measure} & \textbf{Recorded value} \\
\midrule
Accuracy & @@ACC@@\% \\
Balanced accuracy & @@BAL@@\% \\
F1 score & @@FONE@@ \\
ROC-AUC & @@AUC@@ \\
Round duration & @@SECONDS@@ seconds \\
\bottomrule
\end{tabular}
\end{table}
No reviewed-v2 migration or external independence is established by these
metric files. Higher validation accuracy in this later campaign must not be
interpreted as a controlled improvement, a corrected-data result, or evidence
that the earlier leakage concern has been resolved.

'''
for key, value in {'ACC':f"{100*v['accuracy']:.4f}", 'BAL':f"{100*v['balanced_accuracy']:.4f}",
                   'FONE':f"{v['f1']:.6f}", 'AUC':f"{v['roc_auc']:.6f}",
                   'SECONDS':f"{history[0]['seconds']:.2f}"}.items():
    later_section = later_section.replace('@@'+key+'@@', value)
replace(r'\section{Data Leakage Review and Interpretation}', later_section + r'\section{Data Leakage Review and Interpretation}', 'Include omitted later completed campaign, without presenting it as a corrected-data result.')

evidence = r'''\section{Local Evidence Sources and Reproducibility}
The numerical tables were checked against preserved files under
\texttt{multiseed\_outputs/}; they are rounded for presentation, not new
measurements. The principal sources are:
\begin{itemize}
\item \path{multiseed_outputs/architecture/run_20261020T093433_860908Z/validation_metrics.json},
\path{selection.json}, and \path{results_review.json} in that run folder.
\item \path{multiseed_outputs/portal_campaigns/34c72e51-c98a-4a99-be9a-a540dce32a35/history.json}
and \path{result_verification.json} in that campaign folder.
\item \path{multiseed_outputs/portal_campaigns/dbcb01f4-e574-4027-8f54-d9772d08c8d2/history.json},
\path{status.json}, \path{registration.json}, and \path{selection.json} in that folder.
\item \path{multiseed_outputs/hospital_reviewed_v2_latest.json} and
\path{multiseed_outputs/campaign_leakage_review/20261022T080906_451339Z/REPORT.md}.
\end{itemize}
The different runs have different registered data references. Their scores
must not be pooled as repeated seeds or compared as if only the algorithm
changed. No matched FedAvg comparison, patient-cluster confidence interval,
or statistically supported algorithm ranking is established. The original
dataset and historical artifacts were not modified during this report review.

'''
replace('% Chapter 6', evidence + '% Chapter 6', 'Add explicit result-source paths and comparison boundaries.')

bibliography = r'''\begin{thebibliography}{99}
\addcontentsline{toc}{chapter}{Bibliography}
\bibitem{wang2026bcfl}
X. Wang et al., ``Securing Federated Learning With Blockchain in the Medical
Field: Systematic Literature Review,'' \textit{Journal of Medical Internet
Research}, vol. 28, e79052, 2026. \url{https://doi.org/10.2196/79052}.

\bibitem{zhu2023blockfed}
J. Zhu, J. Cao, D. Saxena, S. Jiang, and H. Ferradi,
``Blockchain-Empowered Federated Learning: Challenges, Solutions, and Future
Directions,'' \textit{ACM Computing Surveys}, vol. 55, no. 11, article 240,
2023. \url{https://doi.org/10.1145/3570953}.

\bibitem{shayan2021biscotti}
M. Shayan, C. Fung, C. J. M. Yoon, and I. Beschastnikh,
``Biscotti: A Blockchain System for Private and Secure Federated Learning,''
\textit{IEEE Transactions on Parallel and Distributed Systems}, vol. 32,
no. 7, pp. 1513--1525, 2021.
\url{https://doi.org/10.1109/TPDS.2020.3044223}.

\bibitem{li2021bflc}
Y. Li, C. Chen, N. Liu, H. Huang, Z. Zheng, and Q. Yan,
``A Blockchain-Based Decentralized Federated Learning Framework with Committee
Consensus,'' \textit{IEEE Network}, vol. 35, no. 1, pp. 234--241, 2021.
\url{https://doi.org/10.1109/MNET.011.2000263}.

\bibitem{ferretti2025resilient}
S. Ferretti, L. Cassano, G. Cialone, J. D'Abramo, and F. Imboccioli,
``Decentralized coordination for resilient federated learning: A blockchain-based
approach with smart contracts and decentralized storage,''
\textit{Computer Communications}, article 108112, 2025.
\url{https://doi.org/10.1016/j.comcom.2025.108112}.

\bibitem{miao2022pbfl}
Y. Miao, Z. Liu, H. Li, K. K. R. Choo, and R. H. Deng,
``Privacy-Preserving Byzantine-Robust Federated Learning via Blockchain Systems,''
\textit{IEEE Transactions on Information Forensics and Security}, vol. 17,
pp. 2848--2861, 2022. \url{https://doi.org/10.1109/TIFS.2022.3196274}.

\bibitem{subramanian2022healthcare}
M. Subramanian, V. Rajasekar, Sathishkumar V. E., K. Shanmugavadivel,
and P. S. Nandhini, ``Effectiveness of Decentralized Federated Learning
Algorithms in Healthcare: A Case Study on Cancer Classification,''
\textit{Electronics}, vol. 11, no. 24, article 4117, 2022.
\url{https://doi.org/10.3390/electronics11244117}.

\bibitem{peng2023covid}
L. Peng et al., ``Evaluation of federated learning variations for COVID-19
diagnosis using chest radiographs from 42 US and European hospitals,''
\textit{Journal of the American Medical Informatics Association}, vol. 30,
no. 1, pp. 54--63, 2023 (published online 2022).
\url{https://doi.org/10.1093/jamia/ocac188}.

\bibitem{darzi2024covid}
E. Darzi, N. M. Sijtsema, and P. M. A. van Ooijen,
``A comparative study of federated learning methods for COVID-19 detection,''
\textit{Scientific Reports}, vol. 14, article 3944, 2024.
\url{https://doi.org/10.1038/s41598-024-54323-2}.

\bibitem{rashidi2024detection}
G. Rashidi, D. Bounias, M. Bujotzek, A. Mart\'{i}nez Mora, P. Neher,
and K. H. Maier-Hein, ``The potential of federated learning for self-configuring
medical object detection in heterogeneous data distributions,''
\textit{Scientific Reports}, vol. 14, article 23844, 2024.
\url{https://doi.org/10.1038/s41598-024-74577-0}.

\bibitem{li2020fedprox}
T. Li, A. K. Sahu, M. Zaheer, M. Sanjabi, A. Talwalkar, and V. Smith,
``Federated Optimization in Heterogeneous Networks,''
\textit{Proceedings of Machine Learning and Systems}, vol. 2,
pp. 429--450, 2020. \url{https://arxiv.org/abs/1812.06127}.

\bibitem{he2016resnet}
K. He, X. Zhang, S. Ren, and J. Sun,
``Deep Residual Learning for Image Recognition,''
\textit{Proceedings of the IEEE Conference on Computer Vision and Pattern
Recognition}, pp. 770--778, 2016.
\url{https://openaccess.thecvf.com/content_cvpr_2016/html/He_Deep_Residual_Learning_CVPR_2016_paper.html}.
\end{thebibliography}'''
replace('\\bibliographystyle{IEEEtran}\n\\bibliography{references}', bibliography, 'Embed all bibliography entries so no missing references.bib or IEEEtran.bst dependency remains.')

target = OUT/'fedledger_report_corrected.tex'
target.write_text(text, encoding='utf-8')
notes = '# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain\n\n## LaTeX review — 28 October 2026\n\n'
notes += '\n'.join('- ' + item for item in edits)
notes += '''\n\n## Items still requiring author confirmation\n\n- Institutional facts were supplied by the author and cannot be verified from project code. The certificate names Dr. Saira Varghese as coordinator, while acknowledgements name Dr. Indu M T and Ms. Neethu Krishna as coordinators. Confirm these roles with the department. Names were not guessed or silently replaced.\n- Confirm the Phase I/Semester VII/degree wording, registration numbers, institutional affiliation, faculty titles, submission date and certificate/declaration approval.\n- Supply the approved MITS_LOGO.pdf beside the .tex file; otherwise a visible placeholder is used. Insert the verified similarity report after institutional review.\n- No LaTeX engine (pdflatex, latexmk or tectonic) was found on PATH. Structural checks can be performed, but PDF compilation and visual layout have not been verified.\n- Bibliography metadata and relevant summaries were checked against accessible publisher/author records. ACM blocked direct full-text retrieval; the Zhu DOI/title are retained, but no claim of a new full-text audit is made. The base-paper PDFs and an original references.bib were not supplied with this request.\n- No model training, new evaluation, deployment, or historical evidence modification was performed.\n\n## Selected primary source links\n\n- Biscotti author manuscript: https://www.cs.ubc.ca/~bestchai/papers/tpds20-biscotti.pdf\n- Wang review: https://www.jmir.org/2026/1/e79052/\n- Peng study: https://pmc.ncbi.nlm.nih.gov/articles/PMC9619688/\n- Miao institutional record: https://smusg.elsevierpure.com/en/publications/privacy-preserving-byzantine-robust-federated-learning-via-blockc/\n- Remaining publisher/author links are embedded in the LaTeX bibliography.\n'''
(OUT/'LATEX_REVIEW.md').write_text(notes, encoding='utf-8')
with (ROOT/'RUN_LOG.md').open('a', encoding='utf-8') as stream:
    stream.write('\n'+datetime.now(timezone.utc).isoformat()+' LaTeX review: read user attachment, preserved multiseed result/evidence files, core/workflow/worker/policy/prediction source and architecture docs. Checked relevant paper metadata/claims against publisher/author web sources. Created docs/correct_report_source.py, docs/report/fedledger_report_corrected.tex and docs/report/LATEX_REVIEW.md. Corrected factual claims, bibliography, missing diagram/logo dependencies, later campaign evidence and operational limitations; preserved institutional details for author confirmation. Commands: Get-Content, rg, Get-ChildItem, Get-Command, apply_patch, Python correction builder; web searches/opens. Search wildcard multiseed_outputs\\* failed (invalid Windows wildcard path), replaced by explicit paths. Optional LaTeX tools not found on PATH. ACM returned 403 and MDPI one direct page 429; accessible author/publisher records used where available. No training/data/protocol changes.\n')
print(target)
print('Corrections:', len(edits))
