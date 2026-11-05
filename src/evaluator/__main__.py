import argparse
from pathlib import Path
from evaluator.webapp import serve

def main():
    parser=argparse.ArgumentParser(description='Offline UT Inspection Review')
    parser.add_argument('--project',type=Path,default=Path.home()/ 'UT Inspection Evaluator',help='local project/data directory')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    serve(args.project,args.port,not args.no_browser)

if __name__=='__main__':main()
