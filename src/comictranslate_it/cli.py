"""Command line entrypoint."""
import argparse
import json
from pathlib import Path
from .project import Project
from .pipeline import scan, translate, export
from .reference_benchmark import evaluate, write_profile
from .reference_matching import match_references, save_matches
from .reference_dataset import prepare_dataset
from .annotations import load_annotations, benchmark_archive


def main(argv=None):
    parser=argparse.ArgumentParser(prog="comictranslate",description="ComicTranslate IT v0.5-alpha")
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
    rv=sub.add_parser("reference-eval",help="Allinea una coppia EN/IT (offline) ed estrae metriche")
    rv.add_argument("english");rv.add_argument("italian");rv.add_argument("--part",type=int,default=1)
    rv.add_argument("--out",required=True);rv.add_argument("--overlay",default=None)
    rp=sub.add_parser("reference-profile",help="Stima un profilo da report JSON verificati")
    rp.add_argument("reports",nargs="+");rp.add_argument("--out",required=True)
    ap=sub.add_parser("apply-profile",help="Associa il profilo lettering al progetto")
    ap.add_argument("project");ap.add_argument("profile")
    match=sub.add_parser("reference-match",help="Abbina automaticamente scansioni italiane a pagine CBR/CBZ")
    match.add_argument("archive");match.add_argument("italian",nargs="+");match.add_argument("--out",required=True)
    dataset=sub.add_parser("reference-dataset",help="Abbina, misura e calibra un capitolo EN/IT offline")
    dataset.add_argument("archive");dataset.add_argument("italian",nargs="+")
    dataset.add_argument("--out",required=True);dataset.add_argument("--overlays",action="store_true")
    anno=sub.add_parser('annotate',help='Editor locale per creare annotazioni verificate dei balloon')
    anno.add_argument('archive');anno.add_argument('--out',required=True)
    anno.add_argument('--page',type=int,default=1)
    anno.add_argument('--detector',choices=('baseline','onnx'),default='baseline')
    anno.add_argument('--model-file',default=None)
    anno.add_argument('--threshold',type=float,default=.3)
    check=sub.add_parser('detector-eval',help='Precisione/recall del detector su annotazioni umane')
    check.add_argument('archive');check.add_argument('annotations')
    check.add_argument('--out',required=True)
    check.add_argument('--detector',choices=('baseline','onnx'),default='baseline')
    check.add_argument('--model-file',default=None)
    check.add_argument('--threshold',type=float,default=.3)
    compare=sub.add_parser('detector-compare',help='Confronta detector baseline e ONNX su annotazioni VERIFICATE')
    compare.add_argument('archive');compare.add_argument('annotations')
    compare.add_argument('--model-file',required=True);compare.add_argument('--out',required=True)
    compare.add_argument('--threshold',type=float,default=.3)
    get_model=sub.add_parser('detector-fetch',help='Scarica e verifica il modello ONNX Apache-2.0')
    get_model.add_argument('--out',default='models/detector-v4-s_int8.onnx')
    proposals=sub.add_parser('detector-propose',help='Esporta SOLO box detector, senza toccare fumetto')
    proposals.add_argument('archive');proposals.add_argument('--model-file',required=True)
    proposals.add_argument('--pages',default='5,6,7,8,9,10,11')
    proposals.add_argument('--threshold',type=float,default=.3)
    proposals.add_argument('--out',required=True)
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
            print(f"Abbinati {sum(r['confidence']=='high' for r in report['matches'])}/{len(report['matches'])} riferimenti. Report: {args.out}")
        elif args.action=="reference-dataset":
            report=prepare_dataset(args.archive,args.italian,args.out,args.overlays)
            print(f"Pagine distinte: {report['distinct_matched_pages']}; candidate balloon: {report['balloon_candidates']}; dettagli: {args.out}")
        elif args.action=="reference-eval":
            report=evaluate(args.english,args.italian,args.part,args.overlay)
            Path(args.out).parent.mkdir(parents=True,exist_ok=True)
            Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"Rilevati {report['candidate_balloon_count']} balloon; corrispondenze: {report['alignment']['inliers']}. Report: {args.out}")
        elif args.action=="reference-profile":
            reports=[json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
            profile=write_profile(reports,args.out)
            print(f"Profilo calcolato su {profile['sample_balloon_count']} balloon: fill={profile['target_line_fill']}")
        elif args.action=="apply-profile":
            data=json.loads(Path(args.profile).read_text(encoding="utf-8"))
            fill=data.get("target_line_fill")
            if not isinstance(fill,(float,int)) or not 0.45<=fill<=0.90:
                raise ValueError("Profilo lettering non valido")
            project=Project.load(args.project)
            project.lettering_profile={"target_line_fill":float(fill)}
            project.save()
            print(f"Profilo salvato nel progetto: {fill}")
        elif args.action=='annotate':
            from .annotation_editor import launch as open_annotator
            open_annotator(args.archive,args.out,args.page,args.detector,args.model_file,args.threshold)
        elif args.action=='detector-eval':
            file=Path(args.archive)
            ground_truth=load_annotations(args.annotations,file.name)
            model=None
            if args.detector=='onnx':
                from .learned_detection import LearnedDetector
                if not args.model_file:raise ValueError('Serve --model-file per ONNX')
                model=LearnedDetector(args.model_file)
            result=benchmark_archive(args.archive,ground_truth,detector=args.detector,model=model,threshold=args.threshold)
            output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f"Valutate {len(result['pages'])} pagine: {result['overall']}")
        elif args.action=='detector-compare':
            from .learned_detection import LearnedDetector
            annotation_data=load_annotations(args.annotations,Path(args.archive).name)
            model=LearnedDetector(args.model_file)
            baseline=benchmark_archive(args.archive,annotation_data,detector='baseline')
            learned=benchmark_archive(args.archive,annotation_data,detector='onnx',model=model,threshold=args.threshold)
            comparison={'schema':1,'verified_pages':[p['page'] for p in baseline['pages']],
                'baseline':baseline['overall'],'onnx':learned['overall'],
                'per_page_baseline':baseline['pages'],'per_page_onnx':learned['pages'],
                'note':'Only manually verified pages counted; exact erasure masks NOT assessed.'}
            output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f"Baseline: {baseline['overall']} | ONNX: {learned['overall']}")
        elif args.action=='detector-fetch':
            from .learned_detection import fetch_model
            print(f'Modello SHA-256 verificato: {fetch_model(args.out)}')
        elif args.action=='detector-propose':
            from .learned_detection import LearnedDetector
            from .archives import Archive
            model=LearnedDetector(args.model_file)
            page_numbers=sorted(set(int(x.strip()) for x in args.pages.split(',') if x.strip()))
            result={'schema':1,'model':'ogkalu_rtdetr_v4s_onnx',
                    'verified_ground_truth':False,'pages':{}}
            with Archive(args.archive) as arc:
                for i in page_numbers:
                    if not 1<=i<=len(arc.names):raise ValueError(f'Pagina non valida: {i}')
                    im=arc.image(arc.names[i-1]);detected=model.proposals(im,args.threshold)
                    result['pages'][str(i)]={'filename':arc.names[i-1],
                        'width':im.width,'height':im.height,'regions':detected,
                        'verified':False}
            path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Proposte salvate su {len(page_numbers)} pagine; NON verificate: {path}')
        elif args.action=="gui":
            from .gui import launch
            launch(args.project)
    except (OSError,ValueError,RuntimeError) as exc:
        parser.exit(2,f"ERRORE: {exc}\n")


if __name__=="__main__":
    main()