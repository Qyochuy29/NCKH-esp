"""Inspect existing originals through the running AI, without uploads/DB writes."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filenames',nargs='*')
    parser.add_argument('--limit',type=int,default=6)
    parser.add_argument('--url',default='http://127.0.0.1:5000')
    parser.add_argument('--directory',type=Path,default=Path(os.environ.get('UPLOAD_DIR',
        str(Path(__file__).resolve().parents[1]/'backend-csharp/uploads'))))
    args=parser.parse_args()
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    filenames=args.filenames
    if not filenames:
        extensions={'.wav','.mp3','.m4a','.mp4','.ogg','.webm','.aac'}
        files=sorted((p for p in args.directory.iterdir() if p.is_file() and p.suffix.lower() in extensions),
                     key=lambda p:p.stat().st_mtime,reverse=True)
        filenames=[p.name for p in files[:max(0,args.limit)]]
    for filename in filenames:
        if Path(filename).name!=filename:
            parser.error('Use a filename in the configured upload directory')
        request=Request(args.url.rstrip('/')+'/analyze-full',
            data=json.dumps({'filepath':filename}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=900) as response:
            result=json.load(response)
        print(json.dumps({'file':filename,'asr':result['asr'],'analysis':result['analysis'],
                          'sound_events':result['sound_events'],'timeline':result['timeline']},ensure_ascii=False))


if __name__=='__main__':
    main()
