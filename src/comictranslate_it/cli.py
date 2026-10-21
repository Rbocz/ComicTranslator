"""Command line entrypoint."""
import argparse
import json
from pathlib import Path
from .project import Project
from .pipeline import scan, translate, export


def main(argv=None):
    parser=argparse.ArgumentParser(prog="comictranslate",description="ComicTranslate IT v0.1")
    sub=parser.add_subparsers(dest="action",required=True)
    ini=sub.add_parser("init",help="Crea project.json dall'archivio CBR/CBZ")
    ini.add_argument("source");ini.add_argument("--project",default="project.json")
    ocr=sub.add_parser("scan",help="Proponi regioni OCR senza cancellare pixel")
    ocr.add_argument("project");ocr.add_argument("--min-conf",type=float,default=50)
    ocr.add_argument("--overwrite",action="store_true")
    tr=sub.add_parser("translate",help="Traduzione tramite API, senza approvazione automatica")
    tr.add_argument("project");tr.add_argument("--model",default="gpt-4.1-mini")
    tr.add_argument("--base-url",default="https://api.openai.com/v1")
    ex=sub.add_parser("export",help="Esporta CBZ delle sole regioni approvate")
    ex.add_argument("project");ex.add_argument("--output",required=True)
    ex.add_argument("--font",default=None)
    gu=sub.add_parser("gui",help="Editor per revisione, approvazione e anteprima")
    gu.add_argument("project")
    args=parser.parse_args(argv)
    try:
        if args.action=="init":
            p=Project.create(args.source,args.project)
            print(f"Creato {p.path} ({len(p.pages)} pagine)")
        elif args.action=="scan":
            print(f"Rilevate {scan(Project.load(args.project),args.min_conf,args.overwrite)} regioni OCR (da controllare)")
        elif args.action=="translate":
            print(f"Tradotte {translate(Project.load(args.project),args.model,args.base_url)} regioni (non approvate)")
        elif args.action=="export":
            log=export(Project.load(args.project),args.output,args.font)
            success=sum(r["applied"] for p in log for r in p["regions"])
            blocked=sum(not r["applied"] for p in log for r in p["regions"])
            print(f"Scritto {args.output}. Balloon applicati: {success}; non applicati: {blocked}")
            print(f"Controlli: {Path(args.output).with_suffix('.report.json')}")
        elif args.action=="gui":
            from .gui import launch
            launch(args.project)
    except (OSError,ValueError,RuntimeError) as exc:
        parser.exit(2,f"ERRORE: {exc}\n")


if __name__=="__main__":
    main()
