"""Routes one net's open connection inside a small window of the routed checkpoint (../routed.kicad_pcb).

  .../bin/python3 gen/localroute.py NET x0,y0,x1,y1 [--layers F,B,2] [--commit]

gen/router.py on a grid that covers only the window (board mm), so it takes seconds rather than the many minutes a
whole-board grid takes. Copper outside the window is ignored, so the window must hold both ends of the gap. The
router keeps the board's clearances (0.10 mm; 0.127 mm by POWER-class copper) and the In2 rule (no In2 trace under
a back-layer high-speed trace). Without --commit it only reports whether a path exists.
"""
import re
import sys
import time

import pcbnew

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from autoroute import GRAVE, net_terms  # noqa: E402,F401
from finish import ROUTED  # noqa: E402
from pcb import NETCLASSES, O, W, H  # noqa: E402
from router import Router  # noqa: E402

LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "2": pcbnew.In2_Cu, "1": pcbnew.In1_Cu}


def main():
    net, box = sys.argv[1], tuple(float(v) for v in sys.argv[2].split(","))
    layers = [LAYER[x] for x in (sys.argv[sys.argv.index("--layers") + 1] if "--layers" in sys.argv
                                  else "F,B").split(",")]
    board = pcbnew.LoadBoard(ROUTED)
    R = Router(board, O, (W, H), box, res=0.05, clearance=0.10)
    pw = NETCLASSES["POWER"][-1]
    hs = set()
    for nm, ni in board.GetNetsByName().items():
        short = str(nm).split("/")[-1]
        if re.search(pw, short):
            R.net_cl[ni.GetNetCode()] = 0.127
        if any(re.search(c[-1], short) for k, c in NETCLASSES.items() if k != "POWER"):
            hs.add(ni.GetNetCode())
    R.shadow[pcbnew.In2_Cu] = (pcbnew.B_Cu, hs, 0.3)
    nc = board.FindNet(net).GetNetCode()
    t0 = time.time()
    left = R.connect(net, net_terms(board, nc), 0.1, layers=layers, via=(0.3, 0.15), window=6.0,
                     max_expand=2000000, greed=2.0)
    added = len(R.log)
    print(f"{net}: {'routed' if not left else f'{len(left)} terminals open'} in {time.time() - t0:.1f} s, "
          f"{added} items")
    if not left and "--commit" in sys.argv:
        pcbnew.SaveBoard(ROUTED, board)
        print("saved")


if __name__ == "__main__":
    main()
