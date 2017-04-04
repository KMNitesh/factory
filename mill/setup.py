#!/usr/bin/env python

"""
Prepare or check that the environment is ready for the factory.
"""

__all__ = ['nuke','renew','setup','init']

import os,sys,time,re,shutil,textwrap
from config import read_config,write_config,is_terminal_command,bash,abspath
from makeface import fab
from datapack import asciitree

class FactoryEnv:

	"""
	Run things in a carefully-constructed environment.
	"""

	#---settings for different environments
	meta = {
		'virtualenv':{
			'reqs':['mill/requirements_virtualenv.txt'],
			'setup_kickstart':'setup_virtualenv',
			'setup_refresh':'setup_virtualenv_refresh',
			'loader_commands':{
				'env_activate':'env/bin/activate',
				'env_deactivate':'deactivate'},
			'welcome':'welcome_message',
			'source_cmd':'source env/bin/activate'},
		#---need python2 vs 3
		'anaconda':{
			'reqs_conda':['mill/requirements_anaconda_conda.txt'],
			'reqs_pip':['mill/requirements_anaconda_pip.txt'],
			'setup_kickstart':'setup_anaconda',
			'setup_refresh':'setup_anaconda_refresh',
			'loader_commands':{
				'env_activate':'env/bin/activate',
				'env_deactivate':'deactivate'},
			'welcome':'welcome_message',
			'source_cmd':'source env/bin/activate',
			#---the flag for python2 must happen when the environment is created
			'use_python2':True}}
	#---! need a place to store env path !!! (see above; it's in the activate_script)	
	#---sandbox mimics the virtualenv and uses the same setup, with an extra flag not encoded here
	meta['virtualenv_sandbox'] = dict(meta['virtualenv'])
	meta['virtualenv_sandbox']['setup_kickstart'] = 'setup_virtualenv_sandbox'
	#---folder we always need at root
	required_folders = ['logs','connections']

	def __init__(self,refresh=False):
		"""
		Create a factory environment from instructions in the config, and setup or refresh if necessary.
		"""
		#---create required folders for the factory
		for fn in self.required_folders:
			if not os.path.isdir(fn): os.mkdir(fn)
		#---get a copy of the configuration
		self.config = read_config()
		self.timestamp = self.config.get('setup_stamp',None)
		kind = self.config.get('species',None)
		if kind not in self.meta:
			msg = ('It looks like this is your first time.'
				'To get started with the factory, you have to choose a virtual environment. '
				'Even if you have lots of dank packages installed on your linux box, we still use (at least) '
				'a virtualenv to make sure you have all of the correct dependencies. We recommend '
				'`virtualenv` for users with lots of required packages, `virtualenv_sandbox` for those with '
				'major dependency issues (looking at you, Debian), and `anaconda` for advanced users who '
				'want that sweet, sweet 3D viz and protection against totally screwing up your window '
				'manager.')
			msg_instruct = 'Before continuing, run `make set species <name>` where the name comes '+\
				'from the following list: '
			print('\n'+fab('WELCOME to the FACTORY','cyan_black')+'\n')
			print('\n'.join(textwrap.wrap(msg,width=80)))
			print('\n'+'\n'.join(textwrap.wrap(msg_instruct,width=80))+'\n')
			asciitree({'envs':self.meta.keys()})
			sys.exit(1)
		self.kind = kind
		for key in self.meta[kind]: self.__dict__[key] = self.meta[kind][key]
		#---make sure all requirements files are available no matter what 
		do_refresh = (self.timestamp and self.check_spotchange()) or refresh
		#---environment creation is divided into two parts: first run and refreshes
		start_time = time.time()
		if not self.timestamp: getattr(self,self.setup_kickstart)()
		if not self.timestamp or do_refresh: getattr(self,self.setup_refresh)()
		if do_refresh or not self.timestamp:
			print('[NOTE] setup took %.1f minutes'%((time.time()-start_time)/60.))
		#---register all changes and welcome the user to the plush new environment
		self.register_finished()
		if hasattr(self,self.welcome): getattr(self,self.welcome)()

	def check_spotchange(self):
		"""
		Given a timestamp we see if any of the spots have changed. If they have, we run the refresh routine.
		"""
		reqs_keys = [i for i in self.__dict__ if re.match('^reqs',i)]
		#---loop over keys that start with "reqs" to check requirements files
		for req_type in reqs_keys:
			#---check spotchange only if timestamp is not None
			fns_changed = [fn for fn in self.__dict__[req_type] if 
				int(time.strftime('%Y%m%d%H%M%s',time.localtime(os.path.getmtime(fn))))>int(self.timestamp)]
		#---any requirement change requires a refresh
		#---! note that it might be useful to only run pip install on the ones that change?
		return any(fns_changed)

	def register_finished(self):
		"""
		Update the config.py to make note of the changes to the environment.
		"""
		#---record success and load/unload commands for the environment
		if hasattr(self,'loader_commands'): 
			self.config['activate_env'] = self.loader_commands['env_activate']
		self.config['setup_stamp'] = time.strftime('%Y%m%d%H%M%s')
		write_config(self.config)

	def setup_virtualenv_sandbox(self): 
		"""Wrapper for the sandboxed version of virtualenv setup which requires flag, is v. similar."""
		self.setup_virtualenv(sandbox=True)
 
	def setup_virtualenv(self,sandbox=False):
		"""
		Create a virtualenvironment.
		"""
		def virtualenv_fail(name,extra=None):
			"""
			When virtualenv requires a system package we tell users that anaconda may be an option.
			"""
			message = 'failed to create a virtual environment: missing %s. '%name
			if extra: message += extra
			raise Exception(message)
		if is_terminal_command('virtualenv'): virtualenv_fail('virtualenv')
		#---! automatically start redis? prevent dump.rdb?
		#---preliminary checks
		#---! default redis conf?
		#---! this needs to be somewhere else ??? the whole point of this is to avoid that.
		if False:
			if is_terminal_command('redis-cli'):
				virtualenv_fail('redis-cli',
					extra='if you have redis installed, '+
						'you can run "sudo /usr/sbin/redis-server --daemonize yes". '+
						'if your redis is local (via e.g. anacodna) you can omit "sudo"')
		#---you can sandbox or not
		venv_opts = "--no-site-packages " if sandbox else "--system-site-packages "
		#---note that virtualenv can re-run on the env folder without issue
		bash('virtualenv %senv'%venv_opts,log='logs/log-virtualenv')

	def setup_virtualenv_refresh(self):
		"""
		Refresh the virtualenvironment.
		"""
		for fn in self.reqs:
			print('[STATUS] installing packages via pip from %s'%fn)
			bash(self.source_cmd+' && pip install -r %s'%fn,
				log='logs/log-virtualenv-pip-%s'%os.path.basename(fn))
		#---custom handling for required upgrades
		#---! would be useful to make this systematic
		required_upgrades = ['Sphinx>=1.4.4','numpydoc','sphinx-better-theme','beautifulsoup4']
		#---! here and above we should source the environment first, but this is chicken-egg
		bash(self.source_cmd+' && pip install -U %s'%' '.join([
			"'%s'"%i for i in required_upgrades]),log='logs/log-virtualenv-pip')

	def welcome_message(self):
		"""
		This is identical to the test function in shipping.py.
		"""
		from makeface import fab
		from distutils.spawn import find_executable
		print(fab('ENVIRONMENT:','cyan_black')+' %s'%find_executable('python'))

	def setup_anaconda(self):
		"""
		Set up anaconda.
		"""
		anaconda_location = self.config.get('anaconda_location',None)
		if not anaconda_location: 
			raise Exception('download anaconda and run `make set anaconda_location <path>`')
		install_fn = abspath(anaconda_location)
		if not os.path.isfile(install_fn): raise Exception('cannot find %s'%install_fn)
		bash('bash %s -b -p %s/env'%(install_fn,os.getcwd()))
		if self.use_python2: bash(self.source_cmd+' && conda create python=2 -y -n py2')

	def setup_anaconda_refresh(self):
		"""
		Refresh the virtualenvironment.
		"""
		if self.use_python2:
			self.loader_commands['env_activate'] = 'env/envs/py2/bin/activate py2'
			self.source_cmd = 'source env/envs/py2/bin/activate py2'
		for fn in self.reqs_conda:
			print('[STATUS] installing packages via conda from %s'%fn)
			bash(self.source_cmd+' && conda install -y --file %s'%fn,
				log='logs/log-anaconda-conda-%s'%os.path.basename(fn))
		for fn in self.reqs_pip:
			print('[STATUS] installing packages via pip from %s'%fn)
			bash(self.source_cmd+' && pip install -r %s'%fn,
				log='logs/log-anaconda-conda-%s'%os.path.basename(fn))

def setup(refresh=False):
	"""
	"""
	env = FactoryEnv(refresh=True)
		
def nuke(sure=False):
	"""
	Start from scratch. Erases the environment and  resets the config. You must set the species after this.
	"""
	if sure or all(re.match('^(y|Y)',(input if sys.version_info>(3,0) else raw_input)
		('[QUESTION] %s (y/N)? '%msg))!=None for msg in ['okay to nuke everything','confirm']):
		#---reset procedure starts here
		write_config({
			'commands': ['mill/setup.py','mill/shipping.py','mill/factory.py'],
			'commands_aliases': [('set','set_config')]})
		#---we do not touch the connections, obviously, since you might nuke and reconnect
		#---deleting sensitive stuff here
		for fn in [i for i in ['data'] if os.path.isdir(i)]: shutil.rmtree(fn)
		for dn in ['env','logs','calc','data','pack','site']:
			if os.path.isdir(dn): shutil.rmtree(dn)

def renew(species=None,sure=False):
	"""
	These are test sets for the environment. Be careful -- it erases your current environment!
	"""
	if sure or all(re.match('^(y|Y)',(input if sys.version_info>(3,0) else raw_input)
		('[QUESTION] %s (y/N)? '%msg))!=None for msg in 
		['`renew` is a test set that deletes everything. okay?','confirm']):
		if not species: raise Exception('testset needs a species')
		if species=='virtualenv':
			bash('make nuke sure && make set species virtualenv && make setup && make test')
		elif species=='anaconda':
			bash(' && '.join([
				'make nuke sure',
				'make set species anaconda',
				'make set anaconda_location ~/libs/Anaconda3-4.2.0-Linux-x86_64.sh',
				'make setup',
				'make test']))
		else: raise Exception('no testset for species %s'%species)
		bash('make set omnicalc="http://github.com/bradleyrp/omnicalc"')
		bash('make set automacs="http://github.com/bradleyrp/automacs"')

def init(refresh=False):
	"""
	Language is fluid. Some people want to start with `init`.
	"""
	setup(refresh=refresh)
