"""Render exact source excerpts as presentation-ready PNG code images."""
from pathlib import Path
import hashlib
import json
import textwrap
import zipfile
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name
from project_identity import PROJECT_TITLE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'docs/report/code_screenshots'
OUT.mkdir(exist_ok=True)
FONTS = Path('C:/Windows/Fonts')
code_font = ImageFont.truetype(str(FONTS/'consola.ttf'), 24)
heading_font = ImageFont.truetype(str(FONTS/'segoeuib.ttf'), 31)
meta_font = ImageFont.truetype(str(FONTS/'segoeui.ttf'), 21)
style = get_style_by_name('monokai')
specs = [
    ('01_hospital_registration', 'Hospital membership and approval', 'blockchain/contracts/HospitalDirectory.sol', 'solidity', '    function setMembership', '    }', 'Only the administrator changes membership; the contract emits an auditable event.'),
    ('02_client_authorization', 'Delegated training-client authorization', 'blockchain/contracts/ClientAuthorization.sol', 'solidity', '    function authorize', '    }', 'Approved owners authorize a delegate through the server-verified consent workflow.'),
    ('03_update_submission', 'Register a hospital model update', 'blockchain/contracts/FederatedProtocolRegistry.sol', 'solidity', '    function submitUpdate', '    }', 'Binds the update CID and digest to its signer, round and incoming global model.'),
    ('04_peer_validation', 'On-chain peer-validation decision', 'blockchain/contracts/FederatedProtocolRegistry.sol', 'solidity', '    function submitReview', '    }', 'Confusion counts determine above-chance and non-degradation checks; this is an attestation.'),
    ('05_global_publication', 'Publish the global model reference', 'blockchain/contracts/FederatedProtocolRegistry.sol', 'solidity', '    function publishGlobal', '    }', 'Requires completed reviews; when all updates are rejected, the prior digest is retained.'),
    ('06_fedprox_training', 'Local FedProx optimization', 'fedprox_core.py', 'python', '            optimizer.zero_grad', '            optimizer.step()', 'Class-weighted cross-entropy plus the proximal penalty; training remains off-chain.'),
    ('07_aggregation_weights', 'Validation-aware aggregation weights', 'peer_policy.py', 'python', 'def aggregation_weights', None, 'Accepted mass = local samples x mean peer balanced accuracy; rejected updates get zero weight.'),
    ('08_ipfs_integrity', 'Retrieve and verify an IPFS checkpoint', 'architecture_io.py', 'python', '    def fetch(', '        return target', 'Downloads to a temporary file and checks SHA-256 before exposing the checkpoint.'),
]
manifest=[]
for slug, title, relative, language, start_anchor, end_anchor, note in specs:
    source=ROOT/relative
    lines=source.read_text(encoding='utf-8').splitlines()
    start=next(i for i,line in enumerate(lines) if line.startswith(start_anchor))
    end=(next(i for i in range(start+1,len(lines)) if lines[i] == end_anchor)+1) if end_anchor else len(lines)
    while end>start and not lines[end-1].strip(): end-=1
    excerpt='\n'.join(lines[start:end])+'\n'
    # Dedent presentation whitespace only; source line numbers retain exact provenance.
    presented=textwrap.dedent(excerpt)
    tokens=list(lex(presented,get_lexer_by_name(language)))
    rows=[]; chunks=[]; count=0; source_number=start+1; continuation=False
    def commit():
        global chunks, count, continuation
        rows.append((source_number,continuation,chunks))
        chunks=[];count=0
    for token,value in tokens:
        styled_token=token
        while styled_token not in style._styles:
            styled_token=styled_token.parent
        color=style.style_for_token(styled_token).get('color') or 'e6edf3'
        for part in value.splitlines(keepends=True):
            newline=part.endswith('\n')
            part=part.rstrip('\n').replace('\t','    ')
            while part:
                size=min(94-count,len(part))
                chunks.append((part[:size], '#'+color));count+=size;part=part[size:]
                if count==94 and part:
                    commit();continuation=True
            if newline:
                commit();source_number+=1;continuation=False
    if chunks:commit()
    width=1580; row_height=34; top=170
    height=top+len(rows)*row_height+108
    canvas=Image.new('RGB',(width,height),'#101722');draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((14,14,width-14,height-14),radius=22,fill='#172131',outline='#334155',width=2)
    draw.text((40,29),'FedLedger  /  '+title,font=heading_font,fill='#f1f5f9')
    title_lines=textwrap.wrap(PROJECT_TITLE,110)
    for j,line in enumerate(title_lines):draw.text((40,74+j*26),line,font=meta_font,fill='#9bb0cf')
    draw.text((40,131),f'{relative}   |   lines {start+1}-{end}   |   exact source excerpt',font=meta_font,fill='#68d5c4')
    draw.rectangle((30,top-9,width-30,top+len(rows)*row_height+12),fill='#111827')
    cell=draw.textlength('M',font=code_font)
    for index,(number,cont,pieces) in enumerate(rows):
        y=top+index*row_height
        label='...' if cont else str(number)
        draw.text((45,y),label,font=code_font,fill='#64748b')
        x=130
        for word,color in pieces:
            draw.text((x,y),word,font=code_font,fill=color)
            x+=len(word)*cell
    for j,line in enumerate(textwrap.wrap(note,125)):
        draw.text((40,height-75+j*26),line,font=meta_font,fill='#b8c7de')
    png=OUT/(slug+'.png');canvas.save(png)
    (OUT/(slug+'.txt')).write_text(excerpt,encoding='utf-8')
    manifest.append({'image':png.name,'title':title,'source':relative,'first_line':start+1,'last_line':end,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'note':note,'dimensions':[width,height]})

(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
index='# '+PROJECT_TITLE+'\n\n## Important implementation snippets\n\nThese PNGs are rendered from actual project source, not captures of VS Code. Line numbers and source SHA-256 hashes are recorded in `manifest.json`; wrapped display rows use `...`. The legacy `ModelRegistry.sol` is omitted because active campaigns use `FederatedProtocolRegistry.sol`.\n\n'
for item in manifest:
    index+=f"### {item['title']}\n\n`{item['source']}` lines {item['first_line']}–{item['last_line']}\n\n{item['note']}\n\n![{item['title']}]({item['image']})\n\n"
(OUT/'README.md').write_text(index,encoding='utf-8')
with zipfile.ZipFile(OUT.parent/'fedledger_code_screenshots.zip','w',zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(OUT.iterdir()):
        if path.is_file(): bundle.write(path,'code_screenshots/'+path.name)
with (ROOT/'RUN_LOG.md').open('a',encoding='utf-8') as log:
    log.write('\n'+datetime.now(timezone.utc).isoformat()+' Code snippet image request: read three active Solidity contracts, peer_policy.py, FedProx optimization and IPFS retrieval; inspected Pillow/Pygments and local fonts. Added docs/report/render_code_snippets.py; generated eight source-derived PNGs with source line numbers, exact excerpt text, source hashes, README and ZIP. Commands: Get-Content, rg, Python dependency/font inventory, apply_patch, renderer invocation. No source algorithms/contracts, data, deployments or services changed.\n')
print(json.dumps(manifest,indent=2))
