"""Command line entrypoint."""
import argparse
import json
from pathlib import Path
from .project import Project
from .pipeline import scan, translate, export
from .reference_benchmark import evaluate, write_profile
from .reference_matching import match_references, save_matches
from .reference_dataset import prepare_dataset


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
    rv=sub.add_parser("reference-eval",help="Confronta offline una pagina inglese e quella italiana")
    rv.add_argument("english");rv.add_argument("italian");rv.add_argument("--part",type=int,default=1)
    rv.add_argument("--out",required=True);rv.add_argument("--overlay",default=None)
    rp=sub.add_parser("reference-profile",help="Calibra il lettering da misure di tavole già tradotte")
    rp.add_argument("reports",nargs="+");rp.add_argument("--out",required=True)
    ap=sub.add_parser("apply-profile",help="Associa un profilo misurato al progetto")
    ap.add_argument("project");ap.add_argument("profile")
    rm=sub.add_parser("reference-match",help="Abbina scansioni italiane alle pagine CBR/CBZ")
    rm.add_argument("archive");rm.add_argument("italian",nargs="+");rm.add_argument("--out",required=True)
    ds=sub.add_parser("reference-dataset",help="Abbina, misura e calibra riferimenti EN/IT")
    ds.add_argument("archive");ds.add_argument("italian",nargs="+")
    ds.add_argument("--out",required=True);ds.add_argument("--overlays",action="store_true")
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
        elif args.action=="reference-match":
            report=match_references(args.archive,args.italian)
            save_matches(report,args.out)
            count=sum(x["confidence"]=="high" for x in report["matches"])
            print(f"Abbinati {count}/{len(report['matches'])} riferimenti. Report: {args.out}")
        elif args.action=="reference-dataset":
            report=prepare_dataset(args.archive,args.italian,args.out,args.overlays)
            print(f"Pagine distinte: {report['distinct_matched_pages']}; candidate balloon: {report['balloon_candidates']}; dettagli: {args.out}")
        elif args.action=="reference-eval":
            result=evaluate(args.english,args.italian,args.part,args.overlay)
            Path(args.out).parent.mkdir(parents=True,exist_ok=True)
            Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"Rilevati {result['candidate_balloon_count']} balloon; inliers: {result['alignment']['inliers']}. Report: {args.out}")
        elif args.action=="reference-profile":
            reports=[json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
            result=write_profile(reports,args.out)
            print(f"Profilo su {result['sample_balloon_count']} balloon: fill={result['target_line_fill']}")
        elif args.action=="apply-profile":
            data=json.loads(Path(args.profile).read_text(encoding="utf-8"))
            fill=data.get("target_line_fill")
            if not isinstance(fill,(float,int)) or not 0.45<=fill<=0.90:
                raise ValueError("Profilo lettering non valido")
            p=Project.load(args.project)
            p.lettering_profile={"target_line_fill":float(fill)}
            p.save()
            print(f"Profilo impostato: {fill}")
        elif args.action=="gui":
            from .gui import launch
            launch(args.project)
    except (OSError,ValueError,RuntimeError) as exc:
        parser.exit(2,f"ERRORE: {exc}\n")


if __name__=="__main__":
    main()
