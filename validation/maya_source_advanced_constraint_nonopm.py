"""Non-OPM central driver-frame branch of the literal constraint batch."""
from pathlib import Path

def main(standalone=False,quit_on_finish=True):
 import maya_source_advanced_constraint_matrix as suite
 previous=suite.OUT
 suite.OUT=Path(__file__).resolve().parents[1]/'validation/results/source-advanced-constraint-nonopm-current'
 try:return suite.main(standalone=standalone,quit_on_finish=quit_on_finish,use_opm=False)
 finally:suite.OUT=previous
