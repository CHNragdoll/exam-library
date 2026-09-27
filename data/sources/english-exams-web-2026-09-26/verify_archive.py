"""Current layout verifier; archive scope is the installed 206-paper set."""
import runpy,sys
from pathlib import Path
script=Path(__file__).resolve().parent.parent/'layout-tools'/'verify_layout.py'
sys.path.insert(0,str(script.parent))
sys.argv=[str(script),'--installed']
runpy.run_path(str(script),run_name='__main__')
