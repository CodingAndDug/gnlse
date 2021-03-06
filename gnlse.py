	

import numpy as np
from functools import partial as funcpartial
from scipy.misc import factorial
from scipy.integrate import complex_ode
from time import time
import scipy.io as sio
from matplotlib import pyplot as plt	# you only need this for 'inoutplot'
from mytools import db_abs, db_abs2	# like matplotlib, optictools can be found on github/xmhk

# -----------------------------------------------------------------------------
# CODE OVERVIEW:
#
# 1. FUNCTIONS TO SET PARAMETERS AND PERFORM CALCULATION
# 2. CORE SIMULATION
# 3. DIFFERENT RAMAN RESPONSE FUNCTIONS
# 4. INPUT AND OUTPUT 
# 5. AUXILARY FUNCTIONS
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# 1. FUNCTIONS TO SET PARAMETERS AND PERFORM CALCULATION
# -----------------------------------------------------------------------------

def prepare_sim_params( alpha,
						betas ,
						centerwavelength,						 
						gamma, 
						length,
						N, 
						tempspread=1.0,
						raman = False,
						ramantype = 'hollenbeck',  #or	'blowwood', 'linagrawal'
						fr=0.2,					   #	  0.18			0.245	 
						shock = False,
						nsteps = 500,
						reltol = 1e-6,
						abstol = 1e-9,
						integratortype = 'dopri5',
						zpoints = 256,
						statusmsg = True,
						status_update_intv=1):
	"""
	prepare_simparams
	
	creates a dict containing all information necessary for 
	simulation.
	"""

	# -------------------------------------------------------
	# COMPUTATION GRID
	# -------------------------------------------------------
	
	dt0 = centerwavelength / ( 2.0 * 2.99792458e8) #nyquist
	om0 = 2.0 * np.pi * 2.99792458e8 / centerwavelength	   
	dt = tempspread * dt0
	points = 2**N
	tvec = np.arange( -points/2, points/2) * dt
	relomvec = 2 * np.pi * np.arange (-points/2, points/2)/(points * dt)
	
	omvec = relomvec + om0
	dz = 1.0*length/zpoints	   
	# -------------------------------------------------------
	# LINEAR OPERATOR: dispersion and losses 
	# -------------------------------------------------------
	if len(betas) == points: # dispersion curve as vector
		linop = 1.0j * betas
		bk = betas			 
	else:					 # dispersion via taylor coefficients
		bk = beta0_curve( relomvec, 0, betas)
		linop = 1.0j * bk
	if isinstance(alpha, float):	   # loss (frequency independent)
	   linop += alpha/2.  
	elif isinstance(alpha, np.ndarray) and np.shape(alpha) == np.shape(relomvec): #freq-dep. loss
		linop += alpha/2.
	else:
		print("\n\n WARNING: alpha has to be a float or an array of N points. assuming alpha=0.0\n\n")
		
	linop = np.fft.fftshift(linop)
	# -------------------------------------------------------
	# SHOCK TERM: self-steepening
	# -------------------------------------------------------
	if shock==False:  # self-steepening off
		W = 1.0
	else:			  # self-steepening on
		#gamma = gamma/om0	 # <- original dudley
		#W = relomvec + om0	 # <- original dudley
		#
		# i prefer the version below rather than
		# changing the gamma parameter
		# it should give the same results
		W = omvec / om0
		#
		W = np.fft.fftshift(W)
		
	# -------------------------------------------------------
	# Raman response function
	# -------------------------------------------------------
	#if raman==True:
	#	if ramantype.lower() in ['blowwood','linagrawal','hollenbeck']:
	#		print("Raman response type : %s"%ramantype)
	#		print("response fraction fr: %.3f"%(fr))
	if ramantype=='blowwood':
		RT=raman_blowwood(tvec)
	elif ramantype=='linagrawal':
		RT= raman_linagrawal( tvec )
	elif ramantype=='hollenbeck':
		RT= raman_hollenbeck( tvec )
	else:
		print("\n\nValue Error: ramantype has to be 'blowwood', 'linagrawal' or 'hollenbeck'\n\n")
		raise ValueError()
	RW = points*np.fft.ifft(np.fft.fftshift(RT)) 

	# -------------------------------------------------------
	# PREPARE OUTPUT DICTIONARY
	# -------------------------------------------------------
	Retval = {}	   
	Retval['dt']=dt
	Retval['points']=points
	Retval['tvec']=tvec
	Retval['relomvec']=relomvec
	Retval['om0'] = om0
	Retval['omvec']=omvec
	Retval['dom'] = omvec[2]-omvec[1]
	Retval['raman']=raman
	Retval['fr']=fr
	Retval['RW'] = RW
	Retval['shock']=shock
	Retval['gamma']=gamma
	Retval['linop']=linop
	Retval['betacurve'] = bk
	Retval['length']=1.0 * length
	Retval['W'] = W
	Retval['dz']=dz
	Retval['zpoints']=zpoints	 
	Retval['reltol']=reltol
	Retval['abstol']=abstol
	Retval['nsteps']=nsteps
	Retval['integratortype']=integratortype
	Retval['statusmsg']=statusmsg
	Retval['status_update_intv']=status_update_intv
	return Retval

	
def perform_simulation( simparameters, inifield):  
	"""
	integrate the propagation using a scipy ode solver 
	"""
	integr = prepare_integrator( simparameters, inifield)
	zvec = []
	freqfieldlist = []
	freqfieldlist2 = []
	startingtime = time()
	slength = simparameters['length']
	zvec.append(0)
	freqfieldlist.append(np.fft.ifft( inifield))
	#
	# the fft scalingfactor ensures that the energy is conserved in both domains
	#
	scalefak = np.sqrt( simparameters['dt'] / simparameters['dom'] * simparameters['points'] )
	freqfieldlist2.append(np.fft.fftshift(np.fft.ifft(inifield)) *scalefak)
	for i in range(simparameters['zpoints']):
		if simparameters['statusmsg']:
			if i%int(simparameters['status_update_intv'])==0:
				instatus( integr.t, slength, startingtime)
		integr.integrate(integr.t + simparameters['dz'])
		zvec.append(integr.t)		 
		freqfield = np.multiply ( integr.y , np.exp(simparameters['linop'] * (integr.t) ))
		freqfieldlist.append(freqfield)
		freqfieldlist2.append(np.fft.fftshift(freqfield) * scalefak)
	timefieldarray =np.fft.fft(freqfieldlist)
	return timefieldarray, np.array(freqfieldlist2) ,zvec


def perform_simulation_step( simparameters, inifield):	
	"""
	integrate the propagation using a scipy ode solver 
	"""
	integr = prepare_integrator( simparameters, inifield)
	zvec = []
	#freqfieldlist = []
	#freqfieldlist2 = []
	startingtime = time()
	slength = simparameters['length']
	zvec.append(0)
	#freqfieldlist.append(np.fft.ifft( inifield))
	#
	# the fft scalingfactor ensures that the energy is conserved in both domains
	#
	scalefak = np.sqrt( simparameters['dt'] / simparameters['dom'] * simparameters['points'] )
	#freqfieldlist2.append(np.fft.fftshift(np.fft.ifft(inifield)) *scalefak)
	for i in range(simparameters['zpoints']):
		if simparameters['statusmsg']:
			if i%int(simparameters['status_update_intv'])==0:
				instatus( integr.t, slength, startingtime)
		integr.integrate(integr.t + simparameters['dz'])
		zvec.append(integr.t)		 
		freqfield = np.multiply ( integr.y , np.exp(simparameters['linop'] * (integr.t) ))
		#freqfieldlist.append(freqfield)
		#freqfieldlist2.append(np.fft.fftshift(freqfield) * scalefak)
	del integr
	timefield =np.fft.fft(freqfield)
	#print("verlasse step")
	return timefield ,zvec


	

# -----------------------------------------------------------------------------
# 2. CORE SIMULATION
# -----------------------------------------------------------------------------


def prepare_integrator(simparameters, inifield):
	""" 
	prepare an integration scipy can understand 
	"""
		# only pass the necessary subset of the simparameters dict to GNLSE ...
	simpsub = dict( (k, simparameters[k]) for k in ('gamma','raman','linop','W','dz','dt','RW','fr'))

		# the line below creates a new function handle as some of the scipy integrator functions
		# seem not to wrap additional parameters (simpsub in this case) of the RHS function 
		# correctly	 (as SCIPY 0.14.0.dev-a3e9c7f)
	GNLSE_RHS2 = funcpartial( GNLSE_RHS, simp=simpsub)	  
 
	integrator = complex_ode(GNLSE_RHS2)
		# available types  dop853	dopri5	 lsoda	  vode
		# zvode also available, but do not use, as complex ode handling already wrapped above

	integrator.set_integrator(simparameters['integratortype'], 
							  atol=simparameters['abstol'],
							  rtol=simparameters['reltol'],
							  nsteps=simparameters['nsteps'])

	integrator.set_initial_value(np.fft.ifft( inifield))
	return integrator


def GNLSE_RHS( z, AW, simp):
	"""
	GNLSE_RHS
	solve the generalized Nonlinear Schroedinger equation
	this is derived from the RK4IP matlab script provided in
	"Supercontinuum Generation in Optical Fibers" edited
	by J. M. Dudley and J. R. Taylor (Cambridge 2010).
	see http://scgbook.info/ for the original script.	 
	"""	   
	AT = np.fft.fft( np.multiply( AW , np.exp( simp['linop'] * z)))
	IT = np.abs(AT)**2	
	if simp['raman'] == True:
		RS = simp['dt']	 *	np.fft.fft( np.multiply( np.fft.ifft(IT), simp['RW'] ))
		M = np.fft.ifft( np.multiply( AT,( (1-simp['fr'])*IT +	simp['fr']*RS ) ) )		 
	else:
		M = np.fft.ifft( np.multiply( AT, IT))
	return	1.0j * simp['gamma'] * np.multiply( simp['W'], np.multiply( M, np.exp( -simp['linop'] * z)) )


# -----------------------------------------------------------------------------
# 3. DIFFERENT RAMAN RESPONSE FUNCTIONS
# -----------------------------------------------------------------------------


def raman_blowwood(tvec):
	"""	   
	Raman response function for silica fiber (single Lorentzian) with the model from 

	K. J. Blow and D. Wood, 
	Theoretical description of transient stimulated Raman scattering in optical fibers,
	IEE Journ. of Quant. Electronics, vol 25, no 12, pp 2665-2673, 1989

	value for fr given in the paper fr = 0.18
	"""	 
	tau1 = 12.2e-15
	tau2 = 32.0e-15
	tvec2 = np.multiply( tvec, tvec>=0) # using tvec2 prevents numerical issues for big negative times with exp	  
	rt = (tau1**2 + tau2**2)/(tau1 * tau2**2) *np.multiply( np.exp(-tvec2/tau2), np.sin(tvec2/tau1))
	rt = np.multiply( rt, tvec>=0)
	return rt



def raman_linagrawal(tvec):
	"""
	raman_lin_agrawal(tvec)

	Raman response function for silica fiber (with added Boson peak) with the model from 

	Q. Lin and G. P. Agrawal, 
	Raman response function for silica fibers,
	Opt Lett, vol 31, no 21, pp.3086-3088, 2006

	value for fr given in the paper fr = 0.245
	"""
	tau1 = 12.2e-15
	tau2 = 32.0e-15
	taub=  96.0e-15
	fa=0.75
	fb=0.21
	fc=0.04
	tvec2 = np.multiply( tvec, tvec>=0) # using tvec2 prevents numerical issues for b
	ha = (tau1**2 + tau2**2)/(tau1 * tau2**2) *np.multiply( np.exp(-tvec2/tau2), np.sin(tvec2/tau1))
	hb= (2*taub-tvec2)/taub**2 *  np.exp(-tvec2/taub)
	RT=np.multiply(	 (fa+fc)*ha+fb*hb	 , tvec>0)
	return RT

def raman_hollenbeck(tvec):
	"""	   
	raman_holl(tvec)
	
	Raman response function for silica fiber (quite accurate compared to measured response) with the model from 
	
	D. Hollenbeck and C. Cantrell
	J. Opt. Soc. Am. B / Vol. 19, No. 12 / December 2002
	Multiple-vibrational-mode model for fiber-optic Raman gain
	spectrum and response function Dawn Hollenbeck* and Cyrus D. Cantrell
	PhoTEC, Erik Jonsson School, University of Texas at Dallas, Richardson, Texas 750


	value for fr: not given in the paper. I remember that the experimental fraction shall be  fr = 0.2
	"""
	tvec2 = np.multiply( tvec, tvec>=0) # using tvec2 prevents numerical issues for b
	
	comp_pos=[56.25,100.0,231.25,362.5,463.0,497.0,611.5,
			  691.67,793.67,835.5,930.0,1080.0,1215.0]
	peak_intens=[1.0,11.40,36.67,67.67,74.0,4.5,6.8,
				4.6,4.2,4.5,2.7,3.1,3.0]
	gauss_fwhm=[52.10,110.42,175.00,162.50,135.33,24.5,41.5,155.00,
				59.5,64.3,150.0,91.0,160.0]
	lor_fwhm=[17.37,38.81,58.33,54.17,45.11,8.17,13.83,51.67,
			  19.83,21.43,50.00,30.33,53.33]
	c=2.99792458e8
	biggamma = np.pi * c * np.array(gauss_fwhm)*100
	smallgamma = np.pi * c * np.array(lor_fwhm)*100
	A = np.array(peak_intens)
	ompos = 2 * np.pi * c* np.array(comp_pos)*100
	hr = np.zeros(np.shape(tvec))
	for i in range(13):
		hr += A[i] *np.multiply(np.multiply( np.exp( - tvec2 * smallgamma[i]),
											 np.exp( - biggamma[i]**2 * tvec2**2/4)),
								np.sin(tvec2 * ompos[i]))
	hr = np.multiply( hr, tvec>0)
	dt = tvec[2]-tvec[1]
	hr = hr / (np.sum(hr) * dt)
	return hr




# -----------------------------------------------------------------------------
# 4. INPUT AND OUTPUT 
# -----------------------------------------------------------------------------


def prepare_output_dict(timefieldarray,freqfieldarray,zvec, simparams, xev=1, yev=1):
	"""
	prepare an output dict for saving
	
	INPUT:
	- timefieldarray
	- freqfieldarray
	- zvec
	- simparams dict
	- (optional xev = 1, yev = 1) -> output only every xev-th yevth point

	the dict will contain the following fields:
	- tvec time vector
	- omvec omega vector (absolute)
	- relomvec omega vector (relative)
	- om0 center frequency
	- betacurve dispersion vector
	- length fiber length
	- zpoints number of z steps
	- points time vector points
	- timefield array of field (temporal domain)
	- freqfielf array of field (spectral domain)
	- zvec z vector
	- tfield1, tfield2 in- and output field (temporal domain)
	- ffield1, ffield2 in- and output field (spectral domain domain)
	"""
	outputdict = {}
	lx = len(simparams['tvec'])
	ly = simparams['zpoints']
	outputdict['tvec'] = simparams['tvec'][0:lx:xev]
	outputdict['omvec']=simparams['omvec'][0:lx:xev]
	outputdict['relomvec']=simparams['relomvec'][0:lx:xev]
	outputdict['om0'] = simparams['om0']
	outputdict['betacurve'] = simparams['betacurve'][0:lx:xev]
	outputdict['length']=simparams['length']
	outputdict['zpoints']=simparams['zpoints']
	outputdict['points']=simparams['points']
	
	outputdict['timefield']=timefieldarray[0:ly:yev,0:lx:xev]
	outputdict['freqfield']=freqfieldarray[0:ly:yev,0:lx:xev]
	outputdict['zvec']=zvec[0:ly:yev]

	outputdict['tfield1'] = timefieldarray[0,0:lx:xev]
	outputdict['ffield1'] = freqfieldarray[0,0:lx:xev]
	outputdict['tfield2'] = timefieldarray[simparams['zpoints'],0:lx:xev]
	outputdict['ffield2'] = freqfieldarray[simparams['zpoints'],0:lx:xev]

	return outputdict

def saveoutput(filename, timefieldarray,freqfieldarray,zvec, simparams):
	"""
	saves the output (temporal and spectral field,
	some simparams in one matlab-style file
	
	INPUT:
	- filename
	- timefieldarray
	- freqfieldarray
	- zvec
	- simparams dict
	""" 
	outputdict = prepare_output_dict( timefieldarray,freqfieldarray,zvec, simparams)
	sio.savemat( filename , outputdict)
   


def saveoutput2(filename, timefieldarray,freqfieldarray,zvec, simparams):
	"""
	saves the output (temporal and spectral field,
	some simparams in one matlab-style file
	
	THIS IS DEPRICATED, the function was split into prepare_output_dict
	and saveoutput 

	INPUT:
	- filename
	- timefieldarray
	- freqfieldarray
	- zvec
	- simparams dict

	the saved dict will contain the following fields:
	- tvec time vector
	- omvec omega vector (absolute)
	- relomvec omega vector (relative)
	- om0 center frequency
	- betacurve dispersion vector
	- length fiber length
	- zpoints number of z steps
	- points time vector points
	- timefield array of field (temporal domain)
	- freqfielf array of field (spectral domain)
	- zvec z vector
	- tfield1, tfield2 in- and output field (temporal domain)
	- ffield1, ffield2 in- and output field (spectral domain domain)
	"""
	outputdict = {}
	outputdict['tvec'] = simparams['tvec']
	outputdict['omvec']=simparams['omvec']
	outputdict['relomvec']=simparams['relomvec']
	outputdict['om0'] = simparams['om0']
	outputdict['betacurve'] = simparams['betacurve']
	outputdict['length']=simparams['length']
	outputdict['zpoints']=simparams['zpoints']
	outputdict['points']=simparams['points']
	
	outputdict['timefield']=timefieldarray
	outputdict['freqfield']=freqfieldarray
	outputdict['zvec']=zvec

	outputdict['tfield1'] = timefieldarray[0,:]
	outputdict['ffield1'] = freqfieldarray[0,:]
	outputdict['tfield2'] = timefieldarray[simparams['zpoints'],:]
	outputdict['ffield2'] = freqfieldarray[simparams['zpoints'],:]
	sio.savemat( filename , outputdict)

def loadoutput(filename):
	"""
	load output saved by 'saveoutput'

	INPUT:
	- filename
	
	OUTPUT:
	- a dictionary containing the fields:
		- tvec time vector
		- omvec omega vector (absolute)x
		- relomvec omega vector (relative)
		- om0 center frequency
		- betacurve dispersion vector
		- length fiber length
		- zpoints number of z steps
		- points time vector points
		- timefield array of field (temporal domain)
		- freqfielf array of field (spectral domain)
		- zvec z vector
		- tfield1, tfield2 in- and output field (temporal domain)
		- ffield1, ffield2 in- and output field (spectral domain domain)
	"""
	d=sio.loadmat(filename,squeeze_me=True) #*.mat can only store 2D arrays, squeeze_me is for flattening (vectors)
	return d
	
def extract_outfield_from_dict( outpdict ):
	""" 
	extract only the output field (time, freq)
	and the freq vectors from a dict created
	by mydict  = loadoutput(filename)
   
	returns a Nx7 numpy.array
	"""	   

	tvec  = outpdict['tvec']
	omvec = outpdict['omvec']
	relomvec = outpdict['relomvec']
	tfieldreal = np.real(outpdict['tfield2'])
	tfieldimag = np.imag(outpdict['tfield2'])
	ffieldreal = np.real(outpdict['ffield2'])
	ffieldimag = np.imag(outpdict['ffield2'])
	M = np.zeros( [len( tvec), 7])
	M[:,0]=tvec
	M[:,1]=omvec
	M[:,2]=relomvec
	M[:,3]=tfieldreal
	M[:,4]=tfieldimag
	M[:,5]=ffieldreal
	M[:,6]=ffieldimag
	return M

class output_field( ):
	""" 
	a quick way to get an output field 
	from a numpy.array extract_outfield_from_dict

	returns an OBJECT with the variables
	
	-self.tvec
	-self.omvec
	-self.relomvec
	-self.nuvecthz
	-self.tfield
	-self.ffield
	-self.Som	energy density (with respect to rad/s)
	-self.Snu	energy density (with respect to Hz)
	"""

	def __init__( self, M):
		self.tvec = M[:,0]
		self.omvec = M[:,1]
		self.nuvecthz = self.omvec/2e12/np.pi
		self.relomvec = M[:,2]
		self.tfield = M[:,3] + 1.0j * M[:,4]
		self.ffield = M[:,5] + 1.0j * M[:,6]
		self.som = np.abs(self.ffield)**2
		self.snu = self.som * np.pi * 2.0
	def test(self):
		dt = self.tvec[2]-self.tvec[1]
		dom = self.omvec[2]-self.omvec[1]
		dnu = dom /2./np.pi
		print(" **** ")
		print(" Zeitenergie : %.5e "%(np.sum( np.abs(self.tfield)**2)*dt))
		print(" Freqnergie (om) : %.5e "%np.sum( self.som * dom))
		print(" Freqnergie (nu) : %.5e "%np.sum( self.snu * dnu ))
		


def inoutplot(d,zparams={}): 
	"""
	plot the input and output (both domains)
	as well as temporal and spectral evolution
	into one figure
	
	INPUT:
	- d: dictionary created by 'loadoutput'
	
	OPTIONAL INPUT:
	- zparams: dict that may contain the fields
	   - 'fignr':fignr
	   - 'clim':(cl1,cl2)	 limit for colorcode (z) limits
	   - 'fylim':(fyl1,fyl2) y-limit for spectral plot


	OUTPUT:
	- ax1,ax2,ax3,ax4 handles of the four subfigures
	"""

	if 'fignr' in zparams.keys():
		plt.figure(zparams['fignr'])
	else:
		plt.figure(99)
	ax1=plt.subplot(221)
	plt.plot( d['tvec'], np.abs(d['tfield2'])**2)
	plt.plot( d['tvec'], np.abs(d['tfield1'])**2,linewidth=1)
	plt.legend(["out","in"],loc=0)


	ax2=plt.subplot(222)
	plt.plot( d['omvec']/2.0/np.pi, db_abs2( d['ffield2']))
	plt.plot( d['omvec']/2.0/np.pi, db_abs2( d['ffield1']),linewidth=1)
	if 'fylim' in zparams.keys():
		plt.ylim(zparams['fylim'])
	plt.legend(["out","in"],loc=0)
	ax3=plt.subplot(223)
	plt.imshow( np.abs(d['timefield'])**2,
				aspect='auto',
				origin='lower',
				extent=( np.min(d['tvec']), np.max(d['tvec']),
						 np.min(d['zvec']), np.max(d['zvec'])))
	plt.colorbar()

	ax4=plt.subplot(224)
	ax=plt.imshow( db_abs2(d['freqfield']),
				   aspect='auto',
				   origin='lower',
					extent=( np.min(d['omvec'])/2.0/np.pi, np.max(d['omvec'])/2.0/np.pi,
						 np.min(d['zvec']), np.max(d['zvec'])))
	plt.colorbar()
	if 'clim' in zparams.keys():
		ax.set_clim(zparams['clim'])

	ax1.set_xlabel("time / s")
	ax1.set_ylabel("power / W")
	ax2.set_xlabel("frequency / Hz")
	ax2.set_ylabel("spectral energy density / dB")
	ax3.set_xlabel("time / s")
	ax3.set_ylabel("z / m")
	ax4.set_xlabel("frequency / Hz")
	ax4.set_ylabel("z / m")	   

	return [ax1,ax2,ax3,ax4]



# -----------------------------------------------------------------------------
# 5. AUXILARY FUNCTIONS
# -----------------------------------------------------------------------------



def beta0_curve(omvec, om0, betas):
	"""
	calculate the dispersion curve via Taylor coefficients
	"""
	bc = np.zeros(len(omvec))
	for i in range(len(betas)):
		bc = bc + betas[i]/factorial(i) * (omvec-om0)**i
	return bc



def instatus( aktl, slength, startingtime ):
	"""
	give the status of the integration (used by perform_simulation)
	"""
	frac =	aktl/slength
	if frac>0.0:
		t2 = time()	   
		tel = t2-startingtime		 
		trem = (1-frac)*tel/frac
		print("%.4f m / %.4f m (%.1f%%) | %.0f s | %.0f s (%.2f h)"%(aktl,slength,frac*100, tel,trem,trem/3600.))
		
		
def simpleSSFM(b2,feld, gamma,length,tvec,zpoints, xev, zev, alpha=0.0):
	""" 
	just a simple implementation of the split step fourier method
	for testing puposes
	
	usage:
	fm, zv = simpleSSFM(b2,field, gamma,length,tvec,zpoints, xev, zev, alpha=0.0)
	
	INPUT: - b2 beta2 GVD parameter
		   - field: numerical input field
		   - gamma nonlinearity parameter
		   - length fiber length
		   - tvec time vector
		   - zpoints discretization points in z
		   - xev, zev: sampling parameters (x-every, y-every)
		   
		   - optional parameter: alpha	   (loss / gain parameter)
	
	OUTPUT:
			- fm: matrix of field
			- zv: z vector for field
	"""
	h = length / zpoints
	dt = tvec[2]-tvec[1]
	relomvec = 2 * np.pi *	np.fft.fftfreq( len(tvec), d=dt)#	 
	linop = np.exp( h/2. *( 1.0j * b2/2. * relomvec**2 + alpha/2.))	  
	feldm = []
	lv = len(relomvec)
	feldm.append( feld[0:lv:xev])
	zvec = [0.0]
	z = 0
	for i in range(1, zpoints+1):
		ofeld = np.fft.ifft(feld)
		ofeld = ofeld * linop
		feld = np.fft.fft(ofeld)
		nop = np.exp(1.0j * h * gamma * np.abs(feld)**2)
		feld = feld * nop
		ofeld = np.fft.ifft(feld)
		ofeld = ofeld * linop
		feld = np.fft.fft(ofeld)		
		z+=h
		if i%zev == 0:
			zvec.append(z)
			feldm.append(feld[0:lv:xev])
	return np.array(zvec), np.array(feldm)			
  