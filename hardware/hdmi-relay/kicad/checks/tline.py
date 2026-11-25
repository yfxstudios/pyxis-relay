"""Odd-mode channel simulation (ngspice): PRBS7 NRZ through an ideal line of the routed length/impedance, source and
load at the protocol's termination; reports the worst-case eye height at the sampling point vs a matched line."""
import subprocess, numpy as np, re
C=299792458.0; EEFF=3.2
def prbs7(n):
    s=0x7f; out=[]
    for _ in range(n):
        b=((s>>6)^(s>>5))&1; s=((s<<1)|b)&0x7f; out.append(b)
    return out
def run(name, zodd, rterm, length_mm, rate, tr_frac=0.3, vswing=0.4):
    ui=1/rate; td=length_mm*1e-3*np.sqrt(EEFF)/C; bits=prbs7(127)*2
    tr=ui*tr_frac; pts=[]; t=0
    for b in bits:
        v=vswing if b else -vswing
        pts+= [f"{t+tr:.4e} {v}", f"{t+ui:.4e} {v}"]; t+=ui
    pwl="0 0 "+" ".join(pts)
    net=f"""* {name}
Vs in 0 PWL({pwl})
Rs in a {rterm}
T1 a 0 b 0 Z0={zodd} TD={td:.4e}
Rl b 0 {rterm}
.tran {ui/40:.3e} {t:.4e}
.control
run
wrdata out_{name}.txt v(b)
quit
.endc
.end
"""
    open(f"{name}.cir","w").write(net)
    subprocess.run(["ngspice","-b",f"{name}.cir"],capture_output=True)
    d=np.loadtxt(f"out_{name}.txt"); tt,vv=d[:,0],d[:,1]
    # sample at bit centres after line delay (second half of the pattern, steady state)
    hs=[];ls=[]
    for k,b in enumerate(bits):
        if k<127: continue
        ts=td+k*ui+ui*0.5+tr/2
        v=np.interp(ts,tt,vv)
        (hs if b else ls).append(v)
    eye=min(hs)-max(ls); ideal=vswing  # matched, unloaded half-swing at load = vswing*0.5*2
    return eye, max(hs)
for name,z,zt,ln,rate in (("pcie_tx_routed",52.2,42.5,61,5e9),("pcie_tx_matched",42.5,42.5,61,5e9),
                          ("usb_bt_routed",56.2,45,93.5,480e6),("usb_bt_matched",45,45,93.5,480e6),
                          ("usb_otg_routed",54.4,45,80.5,480e6)):
    eye,pk=run(name,z,zt,ln,rate)
    print(f"{name:16s} Zodd {z:4.1f} vs term {zt}: eye height {eye*1000:6.1f} mV (of 400 mV ideal), peak {pk*1000:.0f} mV")
