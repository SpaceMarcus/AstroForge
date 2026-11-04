"""Reproducible multi-propellant CEA grids and bounded feed/cooling data.
Run .venv/Scripts/python.exe lite/tools/generate_propellants.py from repo root.
No synthetic chemistry, no fallback and no extrapolation.
"""
import sys, json, math, re, importlib.metadata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from engine.chemistry.rocketcea_backend import RocketCEABackend
from engine.models import InputParameters, ChemistryMode
from rocketcea.input_cards import fuelCards, oxCards
import CoolProp.CoolProp as CP
from rocketprops.rocket_prop import get_prop
from generate_cooling_data import GAS_COLUMNS, COOLANT_COLUMNS, P_AXIS

EVONIK='https://active-oxygens.evonik.com/zh/attachment/140277?rev=9a24167032bd618d7f7ff672a62fa152'
# id, CEA card, CoolProp identity, nominal T, minimum T, maximum T
FUELS=[('rp1','RP_1',None,293.15,288,303),('methane','CH4','Methane',110,105,115),('hydrogen','LH2','Hydrogen',20,18,22),('ethanol','Ethanol','Ethanol',293.15,288,303),('propane','Propane','Propane',230,225,235)]
OX=[('lox','LOX','Oxygen',90,85,95),('n2o','N2O','NitrousOxide',250,245,255),('htp90','Peroxide90',None,293.15,288,303)]
SPECS=[('lox','rp1',[2,2.2,2.4,2.6,2.8,3,3.2]),('lox','methane',[2.5,2.75,3,3.25,3.5,3.75,4]),('lox','hydrogen',[4,4.5,5,5.5,6,6.5,7]),('lox','ethanol',[1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,2]),('lox','propane',[2,2.25,2.5,2.75,3,3.25,3.5]),('n2o','rp1',[4,4.5,5,5.5,6,6.5,7,7.5,8]),('n2o','ethanol',[3,3.5,4,4.5,5,5.5,6]),('n2o','propane',[4,4.5,5,5.5,6,6.5,7,7.5,8,8.5,9]),('htp90','rp1',[5,5.5,6,6.5,7,7.5,8,8.5,9]),('htp90','ethanol',[3.5,4,4.5,5,5.5,6,6.5]),('htp90','propane',[5,5.5,6,6.5,7,7.5,8,8.5,9,9.5,10])]
META={s[0]:s for s in FUELS+OX}
LABELS={'rp1':'RP-1','methane':'Methan','hydrogen':'Wasserstoff','ethanol':'Ethanol','propane':'Propan','lox':'LOX','n2o':'N2O','htp90':'HTP 90 Gew.-%'}
b=RocketCEABackend()
if not b.is_available: raise RuntimeError('Real RocketCEA required')
SOURCE='RocketCEA '+importlib.metadata.version('rocketcea')+' via repository backend'
CP_SOURCE='CoolProp '+importlib.metadata.version('CoolProp')

def state(f,o,p,m,e=20,frozen=False):
 return b.calculate(InputParameters(fuel=META[f][1],oxidizer=META[o][1],chamber_pressure_pa=p*1e5,thrust_n=10000,mixture_ratio=m,expansion_ratio=e,ambient_pressure_pa=0,chemistry_mode=ChemistryMode.FROZEN if frozen else ChemistryMode.EQUILIBRIUM))
def row(s):return [s.c_star_m_s,s.cf_vac,s.chamber_temperature_k,s.exit_pressure_pa/1e5]
def gasrow(f,o,p,m):
 s=state(f,o,p,m);z=state(f,o,p,m,frozen=True);R=8.31446261815324/z.molecular_weight_kg_per_mol
 return [s.cp_j_per_kg_k,s.viscosity_pa_s,s.prandtl_number,s.gamma,s.thermal_conductivity_w_per_m_k,s.chamber_temperature_k,z.cp_j_per_kg_k,z.prandtl_number,z.thermal_conductivity_w_per_m_k,z.cp_j_per_kg_k/(z.cp_j_per_kg_k-R)]
def card(name,cards):
 text=' '.join(cards[name]).strip(); match=re.search(r't\(k\)\s*=\s*([\d.]+)',text,re.I)
 return {'cardName':name,'temperatureK':float(match.group(1)) if match else None,'card':text}

fluids={}
for id,cea,cp,T,lo,hi in FUELS+OX:
 if cp:
  if CP.PhaseSI('T',T,'P',7e6,cp) not in ['liquid','supercritical_liquid']:raise RuntimeError('Not liquid: '+id)
  rho=CP.PropsSI('Dmass','T',T,'P',7e6,cp);mu=get_prop('N2O').ViscAtTdegR(T*1.8)*.1 if id=='n2o' else CP.PropsSI('viscosity','T',T,'P',7e6,cp);pmin=CP.PropsSI('P','T',hi,'Q',0,cp)/1e5
  source=CP_SOURCE+' HEOS::'+cp+' at '+str(T)+' K / 70 bar; constant feed screening values'
  if id=='n2o':source+='; viscosity: RocketProps '+importlib.metadata.version('rocketprops')+' saturated-liquid ViscAtTdegR at 250 K; https://rocketprops.readthedocs.io/en/latest/n2o_prop.html'
 elif id=='rp1':rho,mu,pmin,source=810,.0018,0,'Legacy RP-1 constant screening values; cooling uses n-dodecane surrogate'
 else:rho,mu,pmin,source=1390,.00126,0,'Evonik aeronautics HTP 90 wt% at 20 C: '+EVONIK
 fluids[id]={'rho':rho,'mu':mu,'tMin':lo,'tMax':hi,'temperatureK':T,'minPressureBar':pmin,'label':LABELS[id],'source':source,'referencePressureBar':70 if cp else None}
# Keep default legacy model unchanged; new combinations use the explicitly referenced fluids above.
legacy=json.loads((ROOT/'lite/public/cooling-data.json').read_text())
ethT=[288,293.15]+list(range(300,501,5))
ethValues=[]
for T in ethT:
 values=[]
 for P in P_AXIS:
  phase=CP.PhaseSI('T',T,'P',P*1e5,'Ethanol')
  values.append([CP.PropsSI(k,'T',T,'P',P*1e5,'Ethanol') for k in ['Dmass','Cpmass','viscosity','conductivity','Hmass']] if phase in ['liquid','supercritical_liquid'] else None)
 ethValues.append(values)
ethErrors=[0]*4;ethSamples=0
for i in range(len(ethT)-1):
 for j in range(len(P_AXIS)-1):
  cells=[ethValues[i+a][j+c] for a in [0,1] for c in [0,1]]
  if not all(cells):continue
  T=(ethT[i]+ethT[i+1])/2;P=(P_AXIS[j]+P_AXIS[j+1])/2
  truth=[CP.PropsSI(k,'T',T,'P',P*1e5,'Ethanol') for k in ['Dmass','Cpmass','viscosity','conductivity']]
  for k in range(4):ethErrors[k]=max(ethErrors[k],abs(sum(c[k] for c in cells)/4/truth[k]-1))
  ethSamples+=1
ethanol={'source':CP_SOURCE+' HEOS::Ethanol','axes':{'temperatureK':ethT,'pressureBar':P_AXIS},'columns':COOLANT_COLUMNS,'values':ethValues,'validation':{'sampleCount':ethSamples,'maxSampledRelativeError':dict(zip(COOLANT_COLUMNS[:4],ethErrors))},'allowedPhases':['liquid','supercritical_liquid']}
result={'format':'astroforge-propellant-catalog','version':1,'source':SOURCE,'fluids':fluids,'pairs':{},'cooling':{},'references':['https://rocketcea.readthedocs.io/en/latest/propellants.html','https://coolprop.org/fluid_properties/index.html',EVONIK]}
for o,f,mrs in SPECS:
 id=o+'-'+f
 if id=='lox-rp1':continue
 axes={'pcBar':[10,20,30,40,50,60,70,80],'of':mrs,'eps':[4,6,10,15,20,30,40]}
 vals=[row(state(f,o,p,m,e)) for p in axes['pcBar'] for m in mrs for e in axes['eps']]
 errors=[0]*4;samples=0
 for i in range(7):
  for j in range(len(mrs)-1):
   for k in range(6):
    p=(axes['pcBar'][i]+axes['pcBar'][i+1])/2;m=(mrs[j]+mrs[j+1])/2;e=(axes['eps'][k]+axes['eps'][k+1])/2;truth=row(state(f,o,p,m,e));estimated=[0]*4;logratio=0;ew=math.log(e/axes['eps'][k])/math.log(axes['eps'][k+1]/axes['eps'][k])
    for a in [0,1]:
     for c in [0,1]:
      for d in [0,1]:
       v=vals[((i+a)*len(mrs)+j+c)*7+k+d]
       for q in range(3):estimated[q]+=v[q]/8
       logratio+=math.log(v[3]/axes['pcBar'][i+a])*.25*(ew if d else 1-ew)
    estimated[3]=p*math.exp(logratio)
    errors=[max(old,abs(v/t-1)) for old,v,t in zip(errors,estimated,truth)];samples+=1
 grid={'format':'astroforge-thermo-grid','version':1,'pairId':id,'source':SOURCE,'propellants':LABELS[o]+'/'+LABELS[f],'reactants':{'fuel':card(META[f][1],fuelCards),'oxidizer':card(META[o][1],oxCards)},'axes':axes,'values':vals,'fields':['cstarMS','cfVac','tcK','peBar'],'fluids':{'fuel':fluids[f],'ox':fluids[o]},'validation':{'method':'direct CEA at every cell midpoint','sampleCount':samples,'maxSampledRelativeError':dict(zip(['cstarMS','cfVac','tcK','peBar'],errors)),'limitation':'Sampled interpolation agreement, not an experimental validation or global bound.'}}
 if not all(all(math.isfinite(v) and v>0 for v in r) for r in vals):raise RuntimeError('Invalid CEA state '+id)
 result['pairs'][id]=grid
 if f in ['rp1','ethanol']:
  gases=[[gasrow(f,o,p,m) for m in mrs] for p in axes['pcBar']]
  gerrors=[0]*len(GAS_COLUMNS);gsamples=0
  for i in range(7):
   for j in range(len(mrs)-1):
    truth=gasrow(f,o,(axes['pcBar'][i]+axes['pcBar'][i+1])/2,(mrs[j]+mrs[j+1])/2)
    for k,v in enumerate(truth):gerrors[k]=max(gerrors[k],abs(sum(gases[i+a][j+c][k] for a in [0,1] for c in [0,1])/4/v-1))
    gsamples+=1
  result['cooling'][id]={'source':SOURCE+'; '+CP_SOURCE,'gas':{'source':SOURCE+' '+id,'axes':{'pcBar':axes['pcBar'],'of':mrs},'columns':GAS_COLUMNS,'values':gases,'validation':{'sampleCount':gsamples,'maxSampledRelativeError':dict(zip(GAS_COLUMNS,gerrors))}},'coolant':legacy['coolant'] if f=='rp1' else ethanol}
 print(id,len(vals),'states;',samples,'validation points; max error',max(errors),flush=True)
(ROOT/'lite/public/propellant-data.json').write_text(json.dumps(result,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
print('Written propellant-data.json',flush=True)
