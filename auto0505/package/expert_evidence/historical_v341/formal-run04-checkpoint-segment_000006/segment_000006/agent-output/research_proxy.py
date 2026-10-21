"""Own scalar RF proxy: two-mode data mixed with independent standard noise.
Not the public scorer; used only to reason about schedule shapes.
"""
import math
import json
from pathlib import Path


def velocity(x, t, sigma):
    variance = (1-t)**2*sigma*sigma + t*t
    center = 1-t
    # Posterior mean of equal-weight means +/-1, expressed stably.
    mean = math.tanh(x*center/variance)
    linear = (t-(1-t)*sigma*sigma)/variance
    return -mean+linear*(x-center*mean)


def advance(x, a, b, sigma):
    h=b-a
    mid=x+0.5*h*velocity(x,a,sigma)
    return x+h*velocity(mid,(a+b)*0.5,sigma)


def evaluate(nodes, sigma):
    # Deterministic samples across the positive and negative data modes.
    errors=[]
    for mean in (-1,1):
        for z in (-2,-1.5,-1,-.5,0,.5,1,1.5,2):
            x0=mean+sigma*z
            x=x0
            for a,b in zip(nodes[::-1],nodes[-2::-1]): x=advance(x,a,b,sigma)
            for a,b in zip(nodes,nodes[1:]): x=advance(x,a,b,sigma)
            errors.append((x-x0)**2)
    return sum(errors)/len(errors)

result=[]
for sigma in (.1,.2,.4):
    for mu in (.63,0,-.4,-.63,-1,-1.4):
        for power in (1,1.25,1.5):
            def warp(u):
                if u==0 or u==1: return u
                odds=math.exp(mu)*(u/(1-u))**power
                return odds/(1+odds)
            nodes=[warp(1-i/25) for i in range(26)]
            result.append({'sigma_data':sigma,'mu':mu,'logit_power':power,'proxy_mse':evaluate(nodes,sigma)})
Path('/workspace/agent-output/research_proxy_results.json').write_text(json.dumps(result,indent=2)+'\n')
for sigma in (.1,.2,.4):
    rows=[r for r in result if r['sigma_data']==sigma]
    baseline=next(r['proxy_mse'] for r in rows if r['mu']==.63 and r['logit_power']==1)
    print('data sigma',sigma,'proxy starter MSE',baseline)
    print(json.dumps(sorted(rows,key=lambda r:r['proxy_mse'])[:4],indent=2))
