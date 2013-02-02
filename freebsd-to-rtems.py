#! /usr/bin/python
#
#  Copyright (c) 2009-2012 embedded brains GmbH.  All rights reserved.
#
#   embedded brains GmbH
#   Obere Lagerstr. 30
#   82178 Puchheim
#   Germany
#   <info@embedded-brains.de>
#
#  Copyright (c) 2012 OAR Corporation. All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions
#  are met:
#  1. Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#  2. Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# FreeBSD: http://svn.freebsd.org/base/releng/8.2/sys (revision 222485)

import shutil
import os
import re
import sys
import getopt
import filecmp
import difflib

RTEMS_DIR = "not_set"
FreeBSD_DIR = "not_set"
isVerbose = False
isForward = True
isDryRun = False
isDiffMode = False
isEarlyExit = False
isOnlyMakefile = False
tempFile = "/tmp/tmp_FBRT"
filesProcessed = 0

# currently these all use the MIPS in_cksum method
CPUsNeedingGenericIncksum = [ 
	"avr",
	"bfin",
	"h8300",
	"lm32",
	"m32c",
	"m32r",
	"m68k",
	"nios2",
	"sh",
	"sparc",
	"v850",
]

# currently these all use the MIPS in_cksum method
CPUsSharingPCICodeFromX86 = [ 
	'arm',
	'avr',
	'bfin',
	'h8300',
	'lm32',
	'm32c',
	'm32r',
	'm68k',
	'mips',
	'nios2',
	'powerpc',
	'sh',
	'sparc',
	'sparc64',
	'v850',
]

def usage():
  print "freebsd-to-rtems.py [args]"
  print "  -?|-h|--help     print this and exit"
  print "  -d|--dry-run     run program but no modifications"
  print "  -D|--diff        provide diff of files between trees"
  print "  -e|--early-exit  evaluate arguments, print results, and exit"
  print "  -m|--makefile    just generate Makefile"
  print "  -R|--reverse     default FreeBSD -> RTEMS, reverse that"
  print "  -r|--rtems       RTEMS Libbsd directory"
  print "  -f|--freebsd     FreeBSD SVN directory"
  print "  -v|--verbose     enable verbose output mode"

# Parse the arguments
def parseArguments():
  global RTEMS_DIR, FreeBSD_DIR
  global isVerbose, isForward, isDryRun, isEarlyExit
  global isOnlyMakefile, isDiffMode
  try:
    opts, args = getopt.getopt(sys.argv[1:], "?hdDemRr:f:v",
                 ["help",
                  "help",
                  "dry-run"
                  "diff"
                  "early-exit"
                  "makefile"
                  "reverse"
                  "rtems="
                  "freebsd="
                  "verbose"
                 ]
                )
  except getopt.GetoptError, err:
    # print help information and exit:
    print str(err) # will print something like "option -a not recognized"
    usage()
    sys.exit(2)
  for o, a in opts:
    if o in ("-v", "--verbose"):
      isVerbose = True
    elif o in ("-h", "--help", "-?"):
      usage()
      sys.exit()
    elif o in ("-d", "--dry-run"):
      isDryRun = True
    elif o in ("-D", "--diff"):
      isDiffMode = True
    elif o in ("-e", "--early-exit"):
      isEarlyExit = True
    elif o in ("-m", "--makefile"):
      isOnlyMakefile = True
    elif o in ("-R", "--reverse"):
      isForward = False
    elif o in ("-r", "--rtems"):
      RTEMS_DIR = a
    elif o in ("-f", "--freebsd"):
      FreeBSD_DIR = a
    else:
       assert False, "unhandled option"

parseArguments()
print "Verbose:                " + ("no", "yes")[isVerbose]
print "Dry Run:                " + ("no", "yes")[isDryRun]
print "Diff Mode Enabled:      " + ("no", "yes")[isDiffMode]
print "Only Generate Makefile: " + ("no", "yes")[isOnlyMakefile]
print "RTEMS Libbsd Directory: " + RTEMS_DIR
print "FreeBSD SVN Directory:  " + FreeBSD_DIR
print "Direction:              " + ("reverse", "forward")[isForward]

# Check directory argument was set and exist
def wasDirectorySet(desc, path):
    if path == "not_set":
        print desc + " Directory was not specified on command line"
        sys.exit(2)

    if os.path.isdir( path ) != True:
        print desc + " Directory (" + path + ") does not exist"
        sys.exit(2)

# Were RTEMS and FreeBSD directories specified
wasDirectorySet( "RTEMS", RTEMS_DIR )
wasDirectorySet( "FreeBSD", FreeBSD_DIR )
 
# Are we generating or reverting?
if isForward == True:
    print "Forward from FreeBSD SVN into ", RTEMS_DIR
else:
    print "Reverting from ", RTEMS_DIR
    if isOnlyMakefile == True:
        print "Only Makefile Mode and Reverse are contradictory"
        sys.exit(2)

if isEarlyExit == True:
    print "Early exit at user request"
    sys.exit(0)
 
# Prefix added to FreeBSD files as they are copied into the RTEMS
# build tree.
PREFIX = 'freebsd'

def mapContribPath(path):
	m = re.match('(.*)(' + PREFIX + '/)(contrib/\\w+/)(.*)', path)
	if m:
		path = m.group(1) + m.group(3) + m.group(2) + m.group(4)
	return path

# Move target dependent files under a machine directory
def mapCPUDependentPath(path):
	return path.replace("include/", "include/freebsd/machine/")

# compare and process file only if different
#  + copy or diff depending on execution mode
def processIfDifferent(new, old, src):
  global filesProcessed
  global isVerbose, isDryRun, isEarlyExit
  if not os.path.exists(old) or \
     filecmp.cmp(new, old, shallow=False) == False:
    filesProcessed += 1
    if isDiffMode == False:
      if isVerbose == True:
        print "Move " + src + " to " + old
      if isDryRun == False:
        shutil.move(new, old)
    else:
      #print "Diff " + src
      old_contents = open(old).readlines()
      new_contents = open(new).readlines()
      for line in difflib.unified_diff( \
          old_contents, new_contents, fromfile=src, tofile=new, n=5):
        sys.stdout.write(line)

# fix include paths inside a C or .h file
def fixIncludes(data):
	data = re.sub('#([ \t]*)include <', '#\\1include <' + PREFIX + '/', data)
	data = re.sub('#include <' + PREFIX + '/rtems', '#include <rtems', data)
	data = re.sub('#include <' + PREFIX + '/bsp', '#include <bsp', data)
	data = re.sub('#include "([^"]*)"', '#include <' + PREFIX + '/local/\\1>', data)
	data = re.sub('_H_', '_HH_', data)
	return data

# revert fixing the include paths inside a C or .h file
def revertFixIncludes(data):
	data = re.sub('_HH_', '_H_', data)
	data = re.sub('#include <' + PREFIX + '/local/([^>]*)>', '#include "\\1"', data)
	data = re.sub('#([ \t]*)include <' + PREFIX + '/', '#\\1include <', data)
	return data

class Converter(object):
	def convert(self, src):
		return open(src).read()

	def isConvertible(self):
		return True

class NoConverter(Converter):
	def convert(self, src):
		raise

	def isConvertible(self):
		return False

class EmptyConverter(Converter):
	def convert(self, src):
		return '/* EMPTY */\n'

class FromFreeBSDToRTEMSHeaderConverter(Converter):
	def convert(self, src):
		data = super(FromFreeBSDToRTEMSHeaderConverter, self).convert(src)
		return fixIncludes(data)

class FromRTEMSToFreeBSDHeaderConverter(Converter):
	def convert(self, src):
		data = super(FromRTEMSToFreeBSDHeaderConverter, self).convert(src)
		return revertFixIncludes(data)

class FromFreeBSDToRTEMSSourceConverter(Converter):
	def convert(self, src):
		data = super(FromFreeBSDToRTEMSSourceConverter, self).convert(src)
		data = fixIncludes(data)
		data = '#include <' + PREFIX + '/machine/rtems-bsd-config.h>\n\n' + data
		return data

class FromRTEMSToFreeBSDSourceConverter(Converter):
	def convert(self, src):
		data = super(FromRTEMSToFreeBSDSourceConverter, self).convert(src)
		data = re.sub('#include <' + PREFIX + '/machine/rtems-bsd-config.h>\n\n', '', data)
		data = revertFixIncludes(data)
		return data

class PathComposer(object):
	def composeFreeBSDPath(self, path):
		return FreeBSD_DIR + '/' + path

	def composeRTEMSPath(self, path, prefix):
		path = prefix + PREFIX + '/' + path
		path = mapContribPath(path)
		return path

class RTEMSPathComposer(object):
	def composeFreeBSDPath(self, path):
		return path

	def composeRTEMSPath(self, path, prefix):
		path = prefix + 'rtemsbsd/' + path
		return path

class CPUDependentPathComposer(PathComposer):
	def composeRTEMSPath(self, path, prefix):
		path = super(CPUDependentPathComposer, self).composeRTEMSPath(path, prefix)
		path = mapCPUDependentPath(path)
		return path

class File(object):
	def __init__(self, path, pathComposer, fromFreeBSDToRTEMSConverter, fromRTEMSToFreeBSDConverter):
		self.path = path
		self.pathComposer = pathComposer
		self.fromFreeBSDToRTEMSConverter = fromFreeBSDToRTEMSConverter
		self.fromRTEMSToFreeBSDConverter = fromRTEMSToFreeBSDConverter

	def copy(self, dst, src, converter):
		if converter.isConvertible():
			global tempFile
			try:
				if isDryRun == False:
					os.makedirs(os.path.dirname(dst))
			except OSError:
				pass
			data = converter.convert(src)
			out = open(tempFile, 'w')
			out.write(data)
			out.close()
			processIfDifferent(tempFile, dst, src)

	def copyFromFreeBSDToRTEMS(self):
		src = self.pathComposer.composeFreeBSDPath(self.path)
		dst = self.pathComposer.composeRTEMSPath(self.path, RTEMS_DIR + '/')
		self.copy(dst, src, self.fromFreeBSDToRTEMSConverter)

	def copyFromRTEMSToFreeBSD(self):
		src = self.pathComposer.composeRTEMSPath(self.path, RTEMS_DIR + '/')
		dst = self.pathComposer.composeFreeBSDPath(self.path)
		self.copy(dst, src, self.fromRTEMSToFreeBSDConverter)

	def getMakefileFragment(self):
		return self.pathComposer.composeRTEMSPath(self.path, '')

# Remove the output directory
def deleteOutputDirectory():
	try:
		if isVerbose == True:
			print "Delete Directory - " + RTEMS_DIR + "/freebsd"
		if isVerbose == True:
			print "Delete Directory - " + RTEMS_DIR + "/contrib"
		if isDryRun == True:
			return
		shutil.rmtree(RTEMS_DIR + "/freebsd" )
		shutil.rmtree(RTEMS_DIR + "/contrib" )
	except OSError:
	    pass

# Module Manager - Collection of Modules
class ModuleManager:
	def __init__(self):
		self.modules = []

	def addModule(self, module):
		self.modules.append(module)

	def copyFromFreeBSDToRTEMS(self):
		for m in self.modules:
			m.copyFromFreeBSDToRTEMS()

	def copyFromRTEMSToFreeBSD(self):
		for m in self.modules:
			m.copyFromRTEMSToFreeBSD()

	def createMakefile(self):
		global tempFile
		data = 'include config.inc\n' \
			'\n' \
			'include $(RTEMS_MAKEFILE_PATH)/Makefile.inc\n' \
			'include $(RTEMS_CUSTOM)\n' \
			'include $(PROJECT_ROOT)/make/leaf.cfg\n' \
			'\n' \
			'CFLAGS += -ffreestanding \n' \
			'CFLAGS += -I . \n' \
			'CFLAGS += -I rtemsbsd \n' \
			'CFLAGS += -I rtemsbsd/$(RTEMS_CPU)/include \n' \
			'CFLAGS += -I freebsd/$(RTEMS_CPU)/include \n' \
			'CFLAGS += -I contrib/altq \n' \
			'CFLAGS += -I contrib/pf \n' \
			'CFLAGS += -I copied/rtemsbsd/$(RTEMS_CPU)/include \n' \
			'CFLAGS += -w \n' \
			'CFLAGS += -std=gnu99\n' \
			'CFLAGS += -MT $@ -MD -MP -MF $(basename $@).d\n' \
			'NEED_DUMMY_PIC_IRQ=yes\n' \
			'\n' \
                        '# do nothing default so sed on rtems-bsd-config.h always works.\n' \
                        'SED_PATTERN += -e \'s/^//\'\n' \
			'GENERATED_FILES = rtemsbsd/freebsd/machine/rtems-bsd-config.h\n' \
			'\n'
		data += 'C_FILES =\n'
		for m in self.modules:
			if m.conditionalOn != "none":
				data += 'ifneq ($(' + m.conditionalOn + '),yes)\n'

			for file in m.sourceFiles:
				data += 'C_FILES += ' + file.getMakefileFragment() + '\n'
			for cpu, files in sorted(m.cpuDependentSourceFiles.items()):
				data += 'ifeq ($(RTEMS_CPU), ' + cpu + ')\n'
				for file in files:
					data += 'C_FILES += ' + file.getMakefileFragment() + '\n'
				if cpu in ("arm", "i386", "lm32", "mips", "powerpc", "sparc"):
					data += 'NEED_DUMMY_PIC_IRQ=no\n'
				data += 'endif\n'
			if m.conditionalOn != "none":
				data += 'else\n'
				data += 'SED_PATTERN += -e \'' + m.cppPattern +'\'\n'
				data += 'endif # ' + m.conditionalOn +'\n'
		for cpu in CPUsNeedingGenericIncksum:
			data += 'ifeq ($(RTEMS_CPU), ' + cpu + ')\n' \
				'GENERATED_FILES += copied/rtemsbsd/' + cpu + '/' + cpu + '/in_cksum.c\n' \
				'GENERATED_FILES += copied/rtemsbsd/' + cpu + '/include/freebsd/machine/in_cksum.h\n' \
				'GENERATED_FILES += copied/rtemsbsd/' + cpu + '/' + cpu + '/in_cksum.c\n' \
				'C_FILES += copied/rtemsbsd/' + cpu + '/' + cpu + '/in_cksum.c\n' \
				'endif\n'
		for cpu in CPUsSharingPCICodeFromX86:
			data += 'ifeq ($(RTEMS_CPU), ' + cpu + ')\n' \
				'GENERATED_FILES += copied/rtemsbsd/' + cpu + '/include/freebsd/machine/legacyvar.h\n' \
				'GENERATED_FILES += copied/rtemsbsd/' + cpu + '/include/freebsd/machine/pci_cfgreg.h\n' \
				'GENERATED_FILES += copied/freebsd/' + cpu + '/pci/pci_bus.c\n' \
				'GENERATED_FILES += copied/freebsd/' + cpu + '/' + cpu + '/legacy.c\n' \
				'C_FILES += copied/freebsd/' + cpu + '/pci/pci_bus.c\n' \
				'C_FILES += copied/freebsd/' + cpu + '/' + cpu + '/legacy.c\n' \
				'endif\n'
		data += '\n' \
			'ifeq ($(NEED_DUMMY_PIC_IRQ),yes)\n' \
			'CFLAGS += -I rtems-dummy-pic-irq/include\n' \
			'endif\n' \
			'C_O_FILES = $(C_FILES:%.c=%.o)\n' \
			'C_D_FILES = $(C_FILES:%.c=%.d)\n' \
			'\n' \
			'LIB = libbsd.a\n' \
			'\n' \
			'all: $(LIB) lib_user\n' \
			'\n' \
			'$(LIB): $(GENERATED_FILES) $(C_O_FILES)\n' \
			'\t$(AR) rcu $@ $^\n' \
			'\n' \
			'lib_user: $(LIB) install_bsd\n' \
			'\t$(MAKE) -C freebsd-userspace\n' \
			'\n' \
			'# The following targets use the MIPS Generic in_cksum routine\n'
		data += 'rtemsbsd/freebsd/machine/rtems-bsd-config.h: rtemsbsd/freebsd/machine/rtems-bsd-config.h.in\n'
		data += '\tsed $(SED_PATTERN) <$< >$@\n'
		data += '\n'
		for cpu in CPUsNeedingGenericIncksum:
			dDir = 'copied/rtemsbsd/' + cpu + '/' + cpu + '/'
			sDir = 'freebsd/mips/mips/'
			data += dDir + 'in_cksum.c: ' + sDir + 'in_cksum.c\n' \
				'\ttest -d ' + dDir + ' || mkdir -p ' + dDir + '\n' \
				'\tcp $< $@\n' \
				'\n'
			dDir = 'copied/rtemsbsd/' + cpu + '/include/freebsd/machine/'
			sDir = 'freebsd/mips/include/freebsd/machine/'
			data += dDir + 'in_cksum.h: ' + sDir + 'in_cksum.h\n' \
				'\ttest -d ' + dDir + ' || mkdir -p ' + dDir + '\n' \
				'\tcp $< $@\n' \
				'\n' \

		for cpu in CPUsSharingPCICodeFromX86:
			dDir = 'copied/rtemsbsd/' + cpu + '/include/freebsd/machine/'
			sDir = 'freebsd/i386/include/freebsd/machine/'
			data += dDir + 'legacyvar.h: ' + sDir + 'legacyvar.h\n' \
				'\ttest -d ' + dDir + ' || mkdir -p ' + dDir + '\n' \
				'\tcp $< $@\n' \
				'\n' + \
				dDir + 'pci_cfgreg.h: ' + sDir + 'pci_cfgreg.h\n' \
				'\ttest -d ' + dDir + ' || mkdir -p ' + dDir + '\n' \
				'\tcp $< $@\n' \
				'\n'
			dDir = 'copied/freebsd/' + cpu + '/pci/'
			sDir = 'freebsd/i386/pci/'
			data += dDir + 'pci_bus.c: ' + sDir + 'pci_bus.c\n' \
				'\ttest -d ' + dDir + ' || mkdir -p ' + dDir + '\n' \
				'\tcp $< $@\n' \
				'\n'
			dDir = 'copied/freebsd/' + cpu + '/' + cpu + '/'
			sDir = 'freebsd/i386/i386/'
			data += dDir + 'legacy.c: ' + sDir + 'legacy.c\n' \
				'\ttest -d ' + dDir + ' || mkdir -p ' + dDir + '\n' \
				'\tcp $< $@\n' \
				'\n'

		data += 'CPU_SED  = sed\n' \
			'CPU_SED += -e \'/arm/d\'\n' \
			'CPU_SED += -e \'/i386/d\'\n' \
			'CPU_SED += -e \'/powerpc/d\'\n' \
			'CPU_SED += -e \'/mips/d\'\n' \
			'CPU_SED += -e \'/sparc64/d\'\n' \
			'\n' \
			'install: $(LIB) install_bsd lib_user install_user\n' \
			'\n' \
			'install_bsd: $(LIB)\n' \
			'\tinstall -d $(INSTALL_BASE)/include\n' \
			'\tinstall -c -m 644 $(LIB) $(INSTALL_BASE)\n' \
			'\tcd rtemsbsd; for i in `find freebsd -name \'*.h\'` ; do \\\n' \
			'\t  install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\tcd contrib/altq; for i in `find freebsd -name \'*.h\'` ; do \\\n' \
			'\t  install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\tcd contrib/pf; for i in `find freebsd -name \'*.h\'` ; do \\\n' \
                        '\t  install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\tfor i in `find freebsd -name \'*.h\' | $(CPU_SED)` ; do \\\n' \
			'\t  install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\t-cd freebsd/$(RTEMS_CPU)/include && for i in `find . -name \'*.h\'` ; do \\\n' \
			'\t  install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\t-cd rtemsbsd/$(RTEMS_CPU)/include && \\\n' \
			'\t  for i in `find . -name \'*.h\' | $(CPU_SED)` ; do \\\n' \
			'\t    install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\t-cd copied/rtemsbsd/$(RTEMS_CPU)/include && for i in `find . -name \'*.h\'` ; do \\\n' \
			'\t  install -c -m 644 -D "$$i" "$(INSTALL_BASE)/include/$$i" ; done\n' \
			'\n' \
			'install_user:\n' \
			'\t$(MAKE) -C freebsd-userspace install\n' \
			'\n' \
			'clean:\n' \
			'\trm -f -r $(PROJECT_INCLUDE)/rtems/freebsd\n' \
			'\trm -f $(LIB) $(C_O_FILES) $(C_D_FILES) $(GENERATED_FILES)\n' \
			'\trm -f libbsd.html\n' \
			'\trm -rf copied\n' \
			'\t$(MAKE) -C freebsd-userspace clean\n' \
			'\n' \
			'-include $(C_D_FILES)\n' \
			'\n' \
			'doc: libbsd.html\n' \
			'\n' \
			'libbsd.html: libbsd.txt\n' \
			'\tasciidoc -o libbsd.html libbsd.txt\n'
 
		out = open(tempFile, 'w')
		out.write(data)
		out.close()
		makefile = RTEMS_DIR + '/Makefile'
		processIfDifferent(tempFile, makefile, "Makefile")

def assertHeaderFile(path):
	if path[-2] != '.' or path[-1] != 'h':
		print "*** " + path + " does not end in .h"
		print "*** Move it to a C source file list"
		sys.exit(2)

def assertSourceFile(path):
	if path[-2] != '.' or (path[-1] != 'c' and path[-1] != 'S'):
		print "*** " + path + " does not end in .c"
		print "*** Move it to a header file list"
		sys.exit(2)

# Module - logical group of related files we can perform actions on
class Module:
	def __init__(self, name):
		self.name = name
		self.conditionalOn = "none"
		self.cppPattern = "s///"
		self.headerFiles = []
		self.sourceFiles = []
		self.cpuDependentSourceFiles = {}
		self.dependencies = []

	def copyFromFreeBSDToRTEMS(self):
		for file in self.headerFiles:
			file.copyFromFreeBSDToRTEMS()
		for file in self.sourceFiles:
			file.copyFromFreeBSDToRTEMS()
		for cpu, files in self.cpuDependentSourceFiles.items():
			for file in files:
				file.copyFromFreeBSDToRTEMS()

	def copyFromRTEMSToFreeBSD(self):
		for file in self.headerFiles:
			file.copyFromRTEMSToFreeBSD()
		for file in self.sourceFiles:
			file.copyFromRTEMSToFreeBSD()
		for cpu, files in self.cpuDependentSourceFiles.items():
			for file in files:
				file.copyFromRTEMSToFreeBSD()

	def addFiles(self, currentFiles, newFiles, pathComposer, fromFreeBSDToRTEMSConverter, fromRTEMSToFreeBSDConverter, assertFile):
		for file in newFiles:
			assertFile(file)
			currentFiles.append(File(file, pathComposer, fromFreeBSDToRTEMSConverter, fromRTEMSToFreeBSDConverter))
		return currentFiles

	def addHeaderFiles(self, files):
		self.headerFiles = self.addFiles(self.headerFiles, files, PathComposer(), FromFreeBSDToRTEMSHeaderConverter(), FromRTEMSToFreeBSDHeaderConverter(), assertHeaderFile)

	def addEmptyHeaderFiles(self, files):
		self.headerFiles = self.addFiles(self.headerFiles, files, PathComposer(), EmptyConverter(), NoConverter(), assertHeaderFile)

	def addRTEMSHeaderFiles(self, files):
		self.headerFiles = self.addFiles(self.headerFiles, files, RTEMSPathComposer(), NoConverter(), NoConverter(), assertHeaderFile)

	def addCPUDependentHeaderFiles(self, files):
		self.headerFiles = self.addFiles(self.headerFiles, files, CPUDependentPathComposer(), FromFreeBSDToRTEMSHeaderConverter(), FromRTEMSToFreeBSDHeaderConverter(), assertHeaderFile)

	def addSourceFiles(self, files):
		self.sourceFiles = self.addFiles(self.sourceFiles, files, PathComposer(), FromFreeBSDToRTEMSSourceConverter(), FromRTEMSToFreeBSDSourceConverter(), assertSourceFile)

	def addRTEMSSourceFiles(self, files):
		self.sourceFiles = self.addFiles(self.sourceFiles, files, RTEMSPathComposer(), NoConverter(), NoConverter(), assertSourceFile)

	def addCPUDependentSourceFiles(self, cpu, files):
		if not self.cpuDependentSourceFiles.has_key(cpu):
			self.cpuDependentSourceFiles [cpu] = []
		self.cpuDependentSourceFiles [cpu] = self.addFiles(self.cpuDependentSourceFiles [cpu], files, CPUDependentPathComposer(), FromFreeBSDToRTEMSSourceConverter(), FromRTEMSToFreeBSDSourceConverter(), assertSourceFile)

	def addDependency(self, dep):
		self.dependencies.append(dep)

# Create Module Manager and supporting Modules
#  - initialize each module with set of files associated
mm = ModuleManager()

rtems = Module('rtems')
rtems.addRTEMSHeaderFiles(
	[
		'rtems/machine/atomic.h',
		'rtems/machine/_bus.h',
		'rtems/machine/bus.h',
		'rtems/machine/bus_dma.h',
		'rtems/machine/rtems-bsd-config.h',
		'rtems/machine/clock.h',
		'rtems/machine/endian.h',
		'rtems/macpue/_limits.h',
		'rtems/machine/_align.h',
		'rtems/machine/mutex.h',
		'rtems/machine/param.h',
		'rtems/machine/pcpu.h',
		'rtems/machine/pmap.h',
		'rtems/machine/proc.h',
		'rtems/machine/resource.h',
		'rtems/machine/runq.h',
		'rtems/machine/signal.h',
		'rtems/machine/stdarg.h',
		'rtems/machine/_stdint.h',
		'rtems/machine/_types.h',
		'rtems/machine/ucontext.h',
		'rtems/machine/cpu.h',
		'rtems/machine/rtems-bsd-symbols.h',
		'rtems/machine/rtems-bsd-cache.h',
		'rtems/machine/rtems-bsd-sysinit.h',
		'rtems/machine/rtems-bsd-select.h',
		'rtems/machine/rtems-bsd-taskqueue.h',
		'rtems/machine/rtems-bsd-bus-dma.h',
		'rtems/machine/rtems-bsd-bus-devicet.h',
		'bsd.h',
	]
)
rtems.addRTEMSSourceFiles(
	[
		'dev/usb/controller/ohci_lpc24xx.c',
		'dev/usb/controller/ohci_lpc32xx.c',
		'dev/usb/controller/ehci_mpc83xx.c',
		'src/rtems-bsd-thread0-ucred.c',
		'src/rtems-bsd-cam.c',
		'src/rtems-bsd-nexus.c',
		'src/rtems-bsd-autoconf.c',
		'src/rtems-bsd-delay.c',
		'src/rtems-bsd-mutex.c',
		'src/rtems-bsd-thread.c',
		'src/rtems-bsd-condvar.c',
		'src/rtems-bsd-lock.c',
		'src/rtems-bsd-log.c',
		'src/rtems-bsd-sx.c',
		'src/rtems-bsd-rwlock.c',
		#'src/rtems-bsd-generic.c',
		'src/rtems-bsd-page.c',
		'src/rtems-bsd-panic.c',
		'src/rtems-bsd-synch.c',
		'src/rtems-bsd-signal.c',
		'src/rtems-bsd-init.c',
		'src/rtems-bsd-init-with-irq.c',
		'src/rtems-bsd-assert.c',
		'src/rtems-bsd-jail.c',
		'src/rtems-bsd-shell.c',
		'src/rtems-bsd-syscalls.c',
		'src/rtems-bsd-smp.c',
		#'src/rtems-bsd-socket.c',
		#'src/rtems-bsd-mbuf.c',
		'src/rtems-bsd-malloc.c',
		'src/rtems-bsd-support.c',
		'src/rtems-bsd-bus-dma.c',
		'src/rtems-bsd-bus-dma-mbuf.c',
		'src/rtems-bsd-sysctl.c',
		'src/rtems-bsd-sysctlbyname.c',
		'src/rtems-bsd-sysctlnametomib.c',
		'src/rtems-bsd-taskqueue.c',
		'src/rtems-bsd-timesupport.c',
		'src/rtems-bsd-newproc.c',
		'src/rtems-bsd-vm_glue.c',
		'src/rtems-bsd-copyinout.c',
		'src/rtems-bsd-descrip.c',
		'src/rtems-bsd-conf.c',
		'src/rtems-bsd-subr_param.c',
		'src/rtems-bsd-pci_cfgreg.c',
		'src/rtems-bsd-pci_bus.c',
	]
)
rtems.addEmptyHeaderFiles(
	[
		'cam/cam_queue.h',
		'ddb/db_sym.h',
		'ddb/ddb.h',
		'machine/elf.h',
		'machine/sf_buf.h',
		'machine/smp.h',
		'machine/vm.h',
		#'machine/vmparam.h',
		'local/linker_if.h',
		'local/opt_bce.h',
		'local/opt_ntp.h',
		'security/audit/audit.h',
		'sys/bio.h',
		'sys/copyright.h',
		'sys/cpuset.h',
		'sys/exec.h',
		'sys/fail.h',
		#'sys/limits.h',
		'sys/sleepqueue.h',
		'sys/namei.h',
		'sys/_pthreadtypes.h',
		#'sys/resourcevar.h',
		'sys/sched.h',
		#'sys/select.h',
		'sys/syscallsubr.h',
		'sys/sysent.h',
		'sys/syslimits.h',
		'sys/sysproto.h',
		'sys/stat.h',
		#'sys/time.h',
		'time.h',
		#'sys/timespec.h',
		'sys/_timeval.h',
		#'sys/vmmeter.h',
		#'sys/vnode.h',
		'vm/pmap.h',
		#'vm/uma_int.h',
		#'vm/uma_dbg.h',
		#'vm/vm_extern.h',
		'vm/vm_map.h',
		#'vm/vm_object.h',
		#'vm/vm_page.h',
		'vm/vm_param.h',
		#'vm/vm_kern.h',
		'geom/geom_disk.h',
		#'sys/kdb.h',
		#'libkern/jenkins.h',
		'machine/pcb.h',
		#'net80211/ieee80211_freebsd.h',
		'netgraph/ng_ipfw.h',
		#'sys/sf_buf.h',
	]
)

local = Module('local')
# RTEMS has its own local/pmap.h
local.addHeaderFiles(
	[
		'local/bus_if.h',
		'local/device_if.h',
		'local/opt_bus.h',
		'local/opt_cam.h',
		'local/opt_compat.h',
		'local/opt_ddb.h',
		'local/opt_hwpmc_hooks.h',
		'local/opt_init_path.h',
		'local/opt_ktrace.h',
		'local/opt_printf.h',
		'local/opt_scsi.h',
		'local/opt_usb.h',
		'local/opt_inet.h',
		'local/opt_inet6.h',
		'local/opt_altq.h',
		'local/opt_atalk.h',
		'local/opt_bootp.h',
		'local/opt_bpf.h',
		'local/opt_bus.h',
		'local/opt_cam.h',
		'local/opt_carp.h',
		'local/opt_compat.h',
		'local/opt_config.h',
		'local/opt_cpu.h',
		'local/opt_ddb.h',
		'local/opt_device_polling.h',
		'local/opt_ef.h',
		'local/opt_enc.h',
		'local/opt_hwpmc_hooks.h',
		'local/opt_inet6.h',
		'local/opt_inet.h',
		'local/opt_init_path.h',
		'local/opt_ipdivert.h',
		'local/opt_ipdn.h',
		'local/opt_ipfw.h',
		'local/opt_ipsec.h',
		'local/opt_ipstealth.h',
		'local/opt_ipx.h',
		'local/opt_kdb.h',
		'local/opt_kdtrace.h',
		'local/opt_ktrace.h',
		'local/opt_mbuf_profiling.h',
		'local/opt_mbuf_stress_test.h',
		'local/opt_mpath.h',
		'local/opt_mrouting.h',
		'local/opt_natm.h',
		'local/opt_netgraph.h',
		'local/opt_param.h',
		'local/opt_posix.h',
		'local/opt_pf.h',
		'local/opt_printf.h',
		'local/opt_route.h',
		'local/opt_scsi.h',
		'local/opt_sctp.h',
		'local/opt_tcpdebug.h',
		'local/opt_tdma.h',
		'local/opt_usb.h',
		'local/opt_vlan.h',
		'local/opt_wlan.h',
		'local/opt_zero.h',
		'local/usbdevs_data.h',
		'local/usbdevs.h',
		'local/usb_if.h',
		'local/vnode_if.h',
		'local/vnode_if_newproto.h',
		'local/vnode_if_typedef.h',
		'local/cryptodev_if.h',
		'local/miibus_if.h',
		'local/miidevs.h',
		'local/pci_if.h',
		'local/pcib_if.h',
	]
)
local.addSourceFiles(
	[
		'local/usb_if.c',
		'local/bus_if.c',
		'local/device_if.c',
		'local/cryptodev_if.c',
		'local/miibus_if.c',
		'local/pci_if.c',
		'local/pcib_if.c',
	]
)

devUsb = Module('dev_usb')
devUsb.addHeaderFiles(
	[
		'dev/usb/ufm_ioctl.h',
		'dev/usb/usb_busdma.h',
		'dev/usb/usb_bus.h',
		'dev/usb/usb_cdc.h',
		'dev/usb/usb_controller.h',
		'dev/usb/usb_core.h',
		'dev/usb/usb_debug.h',
		'dev/usb/usb_dev.h',
		'dev/usb/usb_device.h',
		'dev/usb/usbdi.h',
		'dev/usb/usbdi_util.h',
		'dev/usb/usb_dynamic.h',
		'dev/usb/usb_endian.h',
		'dev/usb/usb_freebsd.h',
		'dev/usb/usb_generic.h',
		'dev/usb/usb.h',
		'dev/usb/usbhid.h',
		'dev/usb/usb_hub.h',
		'dev/usb/usb_ioctl.h',
		'dev/usb/usb_mbuf.h',
		'dev/usb/usb_msctest.h',
		'dev/usb/usb_process.h',
		'dev/usb/usb_request.h',
		'dev/usb/usb_transfer.h',
		'dev/usb/usb_util.h',
	]
)
devUsb.addSourceFiles(
	[
		'dev/usb/usb_busdma.c',
		'dev/usb/usb_core.c',
		'dev/usb/usb_debug.c',
		'dev/usb/usb_dev.c',
		'dev/usb/usb_device.c',
		'dev/usb/usb_dynamic.c',
		'dev/usb/usb_error.c',
		'dev/usb/usb_generic.c',
		'dev/usb/usb_handle_request.c',
		'dev/usb/usb_hid.c',
		'dev/usb/usb_hub.c',
		'dev/usb/usb_lookup.c',
		'dev/usb/usb_mbuf.c',
		'dev/usb/usb_msctest.c',
		'dev/usb/usb_parse.c',
		'dev/usb/usb_process.c',
		'dev/usb/usb_request.c',
		'dev/usb/usb_transfer.c',
		'dev/usb/usb_util.c',
	]
)

devUsbAddOn = Module('dev_usb_add_on')
devUsbAddOn.addHeaderFiles(
	[
		'dev/usb/usb_pci.h',
		'dev/usb/usb_compat_linux.h',
	]
)
devUsbAddOn.addSourceFiles(
	[
		'dev/usb/usb_compat_linux.c',
	]
)

devUsbBluetooth = Module('dev_usb_bluetooth')
devUsbBluetooth.addDependency(devUsb)
devUsbBluetooth.addHeaderFiles(
	[
		'dev/usb/bluetooth/ng_ubt_var.h',
	]
)
devUsbBluetooth.addSourceFiles(
	[
		'dev/usb/bluetooth/ng_ubt.c',
		'dev/usb/bluetooth/ubtbcmfw.c',
	]
)

devUsbController = Module('dev_usb_controller')
devUsbController.addDependency(devUsb)
devUsbController.addHeaderFiles(
	[
		'dev/usb/controller/ohci.h',
		'dev/usb/controller/ohcireg.h',
		'dev/usb/controller/ehci.h',
		'dev/usb/controller/ehcireg.h',
	]
)
devUsbController.addSourceFiles(
	[
		'dev/usb/controller/ohci.c',
		'dev/usb/controller/ehci.c',
		'dev/usb/controller/usb_controller.c',
	]
)

devUsbControllerAddOn = Module('dev_usb_controller_add_on')
devUsbControllerAddOn.addDependency(devUsb)
devUsbControllerAddOn.addHeaderFiles(
	[
		'dev/usb/controller/at91dci.h',
		'dev/usb/controller/atmegadci.h',
		'dev/usb/controller/musb_otg.h',
		'dev/usb/controller/uss820dci.h',
	]
)
devUsbControllerAddOn.addSourceFiles(
	[
		'dev/usb/controller/at91dci_atmelarm.c',
		'dev/usb/controller/at91dci.c',
		'dev/usb/controller/atmegadci_atmelarm.c',
		'dev/usb/controller/atmegadci.c',
		'dev/usb/controller/ehci_ixp4xx.c',
		'dev/usb/controller/ehci_pci.c',
		'dev/usb/controller/musb_otg.c',
		'dev/usb/controller/ehci_mbus.c',
		'dev/usb/controller/musb_otg_atmelarm.c',
		'dev/usb/controller/ohci_atmelarm.c',
		'dev/usb/controller/ohci_pci.c',
		'dev/usb/controller/uhci_pci.c',
		'dev/usb/controller/uss820dci_atmelarm.c',
		'dev/usb/controller/uss820dci.c',
	]
)

devUsbInput = Module('dev_usb_input')
devUsbInput.addDependency(devUsb)
devUsbInput.addHeaderFiles(
	[
		'dev/usb/input/usb_rdesc.h',
	]
)
devUsbInput.addSourceFiles(
	[
		'dev/usb/input/uhid.c',
		'dev/usb/input/ukbd.c',
	]
)

devUsbInputMouse = Module('dev_usb_mouse')
devUsbInputMouse.addDependency(devUsb)
devUsbInputMouse.addHeaderFiles(
	[
		'sys/tty.h',
		'sys/mouse.h',
		'sys/ttyqueue.h',
		'sys/ttydefaults.h',
		'sys/ttydisc.h',
		'sys/ttydevsw.h',
		'sys/ttyhook.h',
	]
)
devUsbInputMouse.addSourceFiles(
	[
		'dev/usb/input/ums.c',
	]
)

devUsbMisc = Module('dev_usb_misc')
devUsbMisc.addDependency(devUsb)
devUsbMisc.addHeaderFiles(
	[
		'dev/usb/misc/udbp.h',
	]
)
devUsbMisc.addSourceFiles(
	[
		'dev/usb/misc/udbp.c',
		'dev/usb/misc/ufm.c',
	]
)

devUsbNet = Module('dev_usb_net')
devUsbNet.addDependency(devUsb)
devUsbNet.addHeaderFiles(
	[
		'dev/mii/mii.h',
		'dev/mii/miivar.h',
		'net/bpf.h',
		'net/ethernet.h',
		'net/if_arp.h',
		'net/if_dl.h',
		'net/if.h',
		'net/if_media.h',
		'net/if_types.h',
		'net/if_var.h',
		'net/vnet.h',
		'dev/usb/net/if_cdcereg.h',
		'dev/usb/net/usb_ethernet.h',
	]
)
devUsbNet.addSourceFiles(
	[
		'dev/usb/net/if_cdce.c',
		'dev/usb/net/usb_ethernet.c',
	]
)

devUsbQuirk = Module('dev_usb_quirk')
devUsbQuirk.addDependency(devUsb)
devUsbQuirk.addHeaderFiles(
	[
		'dev/usb/quirk/usb_quirk.h',
	]
)
devUsbQuirk.addSourceFiles(
	[
		'dev/usb/quirk/usb_quirk.c',
	]
)

devUsbSerial = Module('dev_usb_serial')
devUsbSerial.addDependency(devUsb)
devUsbSerial.addHeaderFiles(
	[
		'dev/usb/serial/uftdi_reg.h',
		'dev/usb/serial/usb_serial.h',
	]
)
devUsbSerial.addSourceFiles(
	[
		'dev/usb/serial/u3g.c',
		'dev/usb/serial/uark.c',
		'dev/usb/serial/ubsa.c',
		'dev/usb/serial/ubser.c',
		'dev/usb/serial/uchcom.c',
		'dev/usb/serial/ucycom.c',
		'dev/usb/serial/ufoma.c',
		'dev/usb/serial/uftdi.c',
		'dev/usb/serial/ugensa.c',
		'dev/usb/serial/uipaq.c',
		'dev/usb/serial/ulpt.c',
		'dev/usb/serial/umct.c',
		'dev/usb/serial/umodem.c',
		'dev/usb/serial/umoscom.c',
		'dev/usb/serial/uplcom.c',
		'dev/usb/serial/usb_serial.c',
		'dev/usb/serial/uslcom.c',
		'dev/usb/serial/uvisor.c',
		'dev/usb/serial/uvscom.c',
	]
)

devUsbStorage = Module('dev_usb_storage')
devUsbStorage.addDependency(devUsb)
devUsbStorage.addSourceFiles(
	[
		'dev/usb/storage/umass.c',
	]
)

devUsbStorageAddOn = Module('dev_usb_storage_add_on')
devUsbStorageAddOn.addDependency(devUsb)
devUsbStorageAddOn.addHeaderFiles(
	[
		'dev/usb/storage/rio500_usb.h',
	]
)
devUsbStorageAddOn.addSourceFiles(
	[
		'dev/usb/storage/urio.c',
		'dev/usb/storage/ustorage_fs.c',
	]
)

devUsbTemplate = Module('dev_usb_template')
devUsbTemplate.addDependency(devUsb)
devUsbTemplate.addHeaderFiles(
	[
		'dev/usb/template/usb_template.h',
	]
)
devUsbTemplate.addSourceFiles(
	[
		'dev/usb/template/usb_template.c',
		'dev/usb/template/usb_template_cdce.c',
		'dev/usb/template/usb_template_msc.c',
		'dev/usb/template/usb_template_mtp.c',
	]
)

devUsbWlan = Module('dev_usb_wlan')
devUsbWlan.addDependency(devUsb)
devUsbWlan.addHeaderFiles(
	[
		'dev/usb/wlan/if_rumfw.h',
		'dev/usb/wlan/if_rumreg.h',
		'dev/usb/wlan/if_rumvar.h',
		'dev/usb/wlan/if_uathreg.h',
		'dev/usb/wlan/if_uathvar.h',
		'dev/usb/wlan/if_upgtvar.h',
		'dev/usb/wlan/if_uralreg.h',
		'dev/usb/wlan/if_uralvar.h',
		'dev/usb/wlan/if_zydfw.h',
		'dev/usb/wlan/if_zydreg.h',
	]
)
devUsbWlan.addSourceFiles(
	[
		'dev/usb/wlan/if_rum.c',
		'dev/usb/wlan/if_uath.c',
		'dev/usb/wlan/if_upgt.c',
		'dev/usb/wlan/if_ural.c',
		'dev/usb/wlan/if_zyd.c',
	]
)

devPci = Module('dev_pci')
devPci.addHeaderFiles(
	[
		'dev/pci/pcireg.h',
		'dev/pci/pcivar.h',
	]
)

devUsbBase = Module('dev_usb_base')
devUsbBase.addHeaderFiles(
	[
		'bsm/audit.h',
		'bsm/audit_kevents.h',
		'sys/acl.h',
		'sys/bufobj.h',
		'sys/_bus_dma.h',
		'sys/bus_dma.h',
		'sys/bus.h',
		'sys/callout.h',
		'sys/condvar.h',
		'sys/conf.h',
		#'sys/cpuset.h',
		'sys/ctype.h',
		'sys/endian.h',
		'sys/errno.h',
		'sys/event.h',
		'sys/eventhandler.h',
		'sys/fcntl.h',
		'sys/filedesc.h',
		'sys/file.h',
		'sys/filio.h',
		'sys/ioccom.h',
		# FreeBSD version is in RTEMS since used by readv/writev
		# 'sys/_iovec.h',
		'sys/kernel.h',
		'sys/kobj.h',
		'sys/kthread.h',
		'sys/ktr.h',
		'sys/libkern.h',
		'sys/linker_set.h',
		'sys/_lock.h',
		'sys/lock.h',
		'sys/_lockmgr.h',
		'sys/lockmgr.h',
		'sys/lock_profile.h',
		'sys/lockstat.h',
		'sys/mac.h',
		'sys/malloc.h',
		'sys/mbuf.h',
		'sys/module.h',
		'sys/mount.h',
		'sys/_mutex.h',
		'sys/mutex.h',
		'sys/_null.h',
		'sys/osd.h',
		'sys/param.h',
		'sys/pcpu.h',
		'sys/poll.h',
		'sys/priority.h',
		'sys/priv.h',
		'sys/proc.h',
		'sys/queue.h',
		'sys/refcount.h',
		'sys/resource.h',
		'sys/resourcevar.h',
		'sys/rtprio.h',
		'sys/runq.h',
		'sys/_rwlock.h',
		'sys/rwlock.h',
		'sys/_semaphore.h',
		'sys/selinfo.h',
		'sys/sigio.h',
		'sys/_sigset.h',
		#'sys/sleepqueue.h',
		'sys/socket.h',
		'sys/stddef.h',
		'sys/stdint.h',
		'sys/_sx.h',
		'sys/sx.h',
		'sys/sysctl.h',
		'sys/systm.h',
		'sys/ttycom.h',
		'sys/_types.h',
		'sys/types.h',
		'sys/ucontext.h',
		'sys/ucred.h',
		# FreeBSD version is in RTEMS since used by readv/writev
		# 'sys/uio.h',
		'sys/aio.h',
		'sys/unistd.h',
		'sys/vmmeter.h',
		#'sys/vnode.h',
		'sys/rman.h',
		'sys/reboot.h',
		'sys/bitstring.h',
		'sys/linker.h',
		'vm/uma.h',
		'vm/uma_int.h',
		'vm/uma_dbg.h',
		'vm/vm.h',
		#'vm/vm_page.h',
		'fs/devfs/devfs_int.h',
	]
)
devUsbBase.addSourceFiles(
	[
		'kern/init_main.c',
		'kern/kern_linker.c',
		'kern/kern_mib.c',
		'kern/kern_timeout.c',
		'kern/kern_mbuf.c',
		'kern/kern_module.c',
		'kern/kern_sysctl.c',
		'kern/subr_bus.c',
		'kern/subr_kobj.c',
		#'kern/subr_sleepqueue.c',
		'kern/uipc_mbuf.c',
		'kern/uipc_mbuf2.c',
		'kern/uipc_socket.c',
		'kern/uipc_sockbuf.c',
		'kern/uipc_domain.c',
		#'kern/uipc_syscalls.c',
		'vm/uma_core.c',
	]
)

cam = Module('cam')
cam.addHeaderFiles(
	[
		'sys/ata.h',
		'cam/cam.h',
		'cam/cam_ccb.h',
		'cam/cam_sim.h',
		'cam/cam_xpt_sim.h',
		'cam/scsi/scsi_all.h',
		'cam/scsi/scsi_da.h',
		'cam/ata/ata_all.h',
		'cam/cam_periph.h',
		'cam/cam_debug.h',
		'cam/cam_xpt.h',
	]
)
cam.addSourceFiles(
	[
		'cam/cam.c',
		'cam/scsi/scsi_all.c',
	]
)

devNet = Module('dev_net')
devNet.addHeaderFiles(
	[
		'dev/mii/mii.h',
		'dev/mii/miivar.h',
		'dev/mii/brgphyreg.h',
		'dev/mii/icsphyreg.h',
		'dev/led/led.h',
		'net/bpf.h',
		'net/ethernet.h',
		'net/if_arp.h',
		'net/if_dl.h',
		'net/if.h',
		'net/if_media.h',
		'net/if_types.h',
		'net/if_var.h',
		'net/vnet.h',
	]
)
devNet.addSourceFiles(
	[
		'dev/mii/mii.c',
		'dev/mii/mii_physubr.c',
		'dev/mii/icsphy.c',
		'dev/mii/brgphy.c',
	]
)

devNic = Module('dev_nic')
devNic.addHeaderFiles(
	[
	#	'sys/taskqueue.h',
		'sys/pciio.h',
		'dev/random/randomdev_soft.h',
		'sys/eventvar.h',
		'sys/kenv.h',
		'dev/pci/pci_private.h',
		'dev/pci/pcib_private.h',
		'isa/isavar.h',
		'isa/pnpvar.h',
		'netatalk/at.h',
		'netatalk/endian.h',
		'netatalk/aarp.h',
		'netatalk/at_extern.h',
		'netatalk/at_var.h',
		'netatalk/ddp.h',
		'netatalk/ddp_pcb.h',
		'netatalk/ddp_var.h',
		'netatalk/phase2.h',
		'sys/mman.h',
		'sys/buf.h',
		'sys/mqueue.h',
		'sys/tty.h',
		'sys/ttyqueue.h',
		'sys/ttydisc.h',
		'sys/ttydevsw.h',
		'sys/ttyhook.h',
		'sys/user.h',
	]
)

devNic.addCPUDependentHeaderFiles(
	[
		'arm/include/cpufunc.h',
		'i386/include/specialreg.h',
		'i386/include/md_var.h',
		'i386/include/intr_machdep.h',
		'i386/include/legacyvar.h',
		'i386/include/pci_cfgreg.h',
		'i386/include/cpufunc.h',
		'mips/include/cpufunc.h',
		'mips/include/cpuregs.h',
		'powerpc/include/cpufunc.h',
		'powerpc/include/psl.h',
		'powerpc/include/spr.h',
		'sparc64/include/cpufunc.h',
		'sparc64/include/asi.h',
		'sparc64/include/pstate.h',
	]
)

devNic.addCPUDependentSourceFiles(
	'i386',
	[
		'i386/pci/pci_bus.c',
		'i386/i386/legacy.c',
	]
)
devNic.addSourceFiles(
	[
	#	'kern/subr_taskqueue.c',
		'kern/subr_hints.c',
		'dev/random/harvest.c',
		'libkern/random.c',
		'libkern/arc4random.c',
		'kern/subr_pcpu.c',
		'kern/subr_sbuf.c',
		'kern/subr_rman.c',
		'kern/subr_module.c',
		'libkern/inet_ntoa.c',
		'kern/kern_prot.c',
		'kern/kern_proc.c',
		'kern/kern_time.c',
		'kern/kern_event.c',
		'netinet/tcp_hostcache.c',
		'dev/pci/pci.c',
		'dev/pci/pci_user.c',
		'kern/uipc_accf.c',
		'kern/kern_ntptime.c',
		'kern/kern_environment.c',
		'kern/kern_intr.c',
		'kern/kern_resource.c',
		'kern/subr_bufring.c',
		'dev/led/led.c',
		'kern/subr_unit.c',
		'dev/pci/pci_pci.c',
		'netatalk/aarp.c',
		'netatalk/at_control.c',
		'netatalk/at_rmx.c',
		'netatalk/ddp_input.c',
		'netatalk/ddp_pcb.c',
		'netatalk/ddp_usrreq.c',
		'netatalk/at_proto.c',
		'netatalk/ddp_output.c',
		'kern/sys_generic.c',
		'kern/kern_descrip.c',
		'kern/kern_mtxpool.c',
	]
)

devNic_re = Module('dev_nic_re')
devNic_re.addHeaderFiles(
	[
		'pci/if_rlreg.h',
	]
)
devNic_re.addSourceFiles(
	[
		'dev/re/if_re.c',
	]
)

devNic_fxp = Module('dev_nic_fxp')
devNic_fxp.addHeaderFiles(
	[
		'dev/fxp/if_fxpreg.h',
		'dev/fxp/if_fxpvar.h',
		'dev/fxp/rcvbundl.h',
	]
)
devNic_fxp.addSourceFiles(
	[
		'dev/fxp/if_fxp.c',
	]
)

devNic_e1000 = Module('dev_nic_e1000')
devNic_e1000.addHeaderFiles(
	[
		'dev/e1000/e1000_80003es2lan.h',
		'dev/e1000/e1000_82571.h',
		'dev/e1000/e1000_defines.h',
		'dev/e1000/e1000_mac.h',
		'dev/e1000/e1000_nvm.h',
		'dev/e1000/e1000_regs.h',
		'dev/e1000/if_igb.h',
		'dev/e1000/e1000_82541.h',
		'dev/e1000/e1000_82575.h',
		'dev/e1000/e1000_hw.h',
		'dev/e1000/e1000_manage.h',
		'dev/e1000/e1000_osdep.h',
		'dev/e1000/e1000_vf.h',
		'dev/e1000/if_lem.h',
		'dev/e1000/e1000_82543.h',
		'dev/e1000/e1000_api.h',
		'dev/e1000/e1000_ich8lan.h',
		'dev/e1000/e1000_mbx.h',
		'dev/e1000/e1000_phy.h',
		'dev/e1000/if_em.h',
	]
)
devNic_e1000.addSourceFiles(
	[
		'dev/e1000/e1000_80003es2lan.c',
		'dev/e1000/e1000_82542.c',
		'dev/e1000/e1000_82575.c',
		'dev/e1000/e1000_mac.c',
		'dev/e1000/e1000_nvm.c',
		'dev/e1000/e1000_vf.c',
		'dev/e1000/if_lem.c',
		'dev/e1000/e1000_82540.c',
		'dev/e1000/e1000_82543.c',
		'dev/e1000/e1000_api.c',
		'dev/e1000/e1000_manage.c',
		'dev/e1000/e1000_osdep.c',
		'dev/e1000/if_em.c',
		'dev/e1000/e1000_82541.c',
		'dev/e1000/e1000_82571.c',
		'dev/e1000/e1000_ich8lan.c',
		'dev/e1000/e1000_mbx.c',
		'dev/e1000/e1000_phy.c',
		'dev/e1000/if_igb.c',
	]
)

# DEC Tulip aka Intel 21143
devNic_dc = Module('dev_nic_dc')
devNic_dc.addHeaderFiles(
	[
		'dev/dc/if_dcreg.h',
	]
)
devNic_dc.addSourceFiles(
	[
		'dev/dc/dcphy.c',
		'dev/dc/if_dc.c',
		'dev/dc/pnphy.c',
	]
)

# SMC9111x
devNic_smc = Module('dev_nic_smc')
devNic_smc.addHeaderFiles(
	[
		'dev/smc/if_smcreg.h',
		'dev/smc/if_smcvar.h',
	]
)
devNic_smc.addSourceFiles(
	[
		'dev/smc/if_smc.c',
	]
)

# Crystal Semiconductor CS8900
devNic_cs = Module('dev_nic_cs')
devNic_cs.addHeaderFiles(
	[
		'dev/cs/if_csreg.h',
		'dev/cs/if_csvar.h',
	]
)
devNic_cs.addSourceFiles(
	[
		'dev/cs/if_cs.c',
		'dev/cs/if_cs_isa.c',
		'dev/cs/if_cs_pccard.c',
	]
)

# Broadcomm BCE, BFE, BGE - MII is intertwined
devNic_broadcomm = Module('dev_nic_broadcomm')
devNic_broadcomm.addHeaderFiles(
	[
		'dev/bce/if_bcefw.h',
		'dev/bce/if_bcereg.h',
		'dev/bfe/if_bfereg.h',
		'dev/bge/if_bgereg.h',
	]
)
devNic_broadcomm.addSourceFiles(
	[
		'dev/bce/if_bce.c',
		'dev/bfe/if_bfe.c',
		'dev/bge/if_bge.c',
	]
)

netDeps = Module('netDeps')
netDeps.addHeaderFiles(
	[
		'security/mac/mac_framework.h',
		'sys/cpu.h',
		'sys/interrupt.h',
		'sys/fnv_hash.h',
		'sys/tree.h',
		'sys/buf_ring.h',
		'sys/rwlock.h',
		'sys/_rmlock.h',
		'sys/sockio.h',
		'sys/sdt.h',
		'sys/_task.h',
		'sys/sbuf.h',
		'sys/smp.h',
		'sys/syslog.h',
		'sys/jail.h',
		'sys/protosw.h',
		'sys/random.h',
		'sys/rmlock.h',
		'sys/hash.h',
		#'sys/select.h',
		'sys/sf_buf.h',
		'sys/socketvar.h',
		'sys/sockbuf.h',
		#'sys/sysproto.h',
		'sys/sockstate.h',
		'sys/sockopt.h',
		'sys/domain.h',
		'sys/time.h',
	]
)

net = Module('net')
net.addHeaderFiles(
	[
		'net/bpf_buffer.h',
		'net/bpfdesc.h',
		'net/bpf.h',
		'net/bpf_jitter.h',
		'net/bpf_zerocopy.h',
		'net/bridgestp.h',
		'net/ethernet.h',
		'net/fddi.h',
		'net/firewire.h',
		'net/flowtable.h',
		'net/ieee8023ad_lacp.h',
		'net/if_arc.h',
		'net/if_arp.h',
		'net/if_atm.h',
		'net/if_bridgevar.h',
		'net/if_clone.h',
		'net/if_dl.h',
		'net/if_enc.h',
		'net/if_gif.h',
		'net/if_gre.h',
		'net/if.h',
		'net/if_lagg.h',
		'net/if_llatbl.h',
		'net/if_llc.h',
		'net/if_media.h',
		'net/if_mib.h',
		'net/if_sppp.h',
		'net/if_stf.h',
		'net/if_tap.h',
		'net/if_tapvar.h',
		'net/if_tun.h',
		'net/if_types.h',
		'net/if_var.h',
		'net/if_vlan_var.h',
		'net/iso88025.h',
		'net/netisr.h',
		'net/pfil.h',
		'net/pfkeyv2.h',
		'net/ppp_defs.h',
		'net/radix.h',
		'net/radix_mpath.h',
		'net/raw_cb.h',
		'net/route.h',
		'net/slcompress.h',
		'net/vnet.h',
		'net/zlib.h',
		'sys/timepps.h',
		'sys/timetc.h',
		'sys/timex.h',
	]
)
net.addSourceFiles(
	[
		'kern/subr_eventhandler.c',
		'kern/kern_subr.c',
		'kern/kern_tc.c',
		'libkern/fls.c',
		'net/bridgestp.c',
		'net/ieee8023ad_lacp.c',
		'net/if_atmsubr.c',
		'net/if.c',
		'net/if_clone.c',
		'net/if_dead.c',
		'net/if_disc.c',
		'net/if_edsc.c',
		'net/if_ef.c',
		'net/if_enc.c',
		'net/if_epair.c',
		'net/if_faith.c',
		'net/if_fddisubr.c',
		'net/if_fwsubr.c',
		'net/if_gif.c',
		'net/if_gre.c',
		'net/if_iso88025subr.c',
		'net/if_lagg.c',
		'net/if_llatbl.c',
		'net/if_loop.c',
		'net/if_media.c',
		'net/if_mib.c',
		'net/if_spppfr.c',
		'net/if_spppsubr.c',
		'net/if_tap.c',
		'net/if_tun.c',
		'net/if_vlan.c',
		'net/pfil.c',
		'net/radix.c',
		'net/radix_mpath.c',
		'net/raw_cb.c',
		'net/raw_usrreq.c',
		'net/route.c',
		'net/rtsock.c',
		'net/slcompress.c',
		'net/zlib.c',
		'net/bpf_buffer.c',
		'net/bpf.c',
		'net/bpf_filter.c',
		'net/bpf_jitter.c',
		'net/if_arcsubr.c',
		'net/if_bridge.c',
		'net/if_ethersubr.c',
		'net/netisr.c',
	]
)

netinet = Module('netinet')
netinet.addHeaderFiles(
	[
		'netinet/icmp6.h',
		'netinet/icmp_var.h',
		'netinet/if_atm.h',
		'netinet/if_ether.h',
		'netinet/igmp.h',
		'netinet/igmp_var.h',
		'netinet/in_gif.h',
		'netinet/in.h',
		'netinet/in_pcb.h',
		'netinet/in_systm.h',
		'netinet/in_var.h',
		'netinet/ip6.h',
		'netinet/ip_carp.h',
		'netinet/ip_divert.h',
		'netinet/ip_dummynet.h',
		'netinet/ip_ecn.h',
		'netinet/ip_encap.h',
		'netinet/ip_fw.h',
		'netinet/ip_gre.h',
		'netinet/ip.h',
		'netinet/ip_icmp.h',
		'netinet/ip_ipsec.h',
		'netinet/ip_mroute.h',
		'netinet/ip_options.h',
		'netinet/ip_var.h',
		'netinet/ipfw/ip_dn_private.h',
		'netinet/ipfw/ip_fw_private.h',
		'netinet/ipfw/dn_sched.h',
		'netinet/ipfw/dn_heap.h',
		'netinet/pim.h',
		'netinet/pim_var.h',
		'netinet/sctp_asconf.h',
		'netinet/sctp_auth.h',
		'netinet/sctp_bsd_addr.h',
		'netinet/sctp_cc_functions.h',
		'netinet/sctp_constants.h',
		'netinet/sctp_crc32.h',
		'netinet/sctp.h',
		'netinet/sctp_header.h',
		'netinet/sctp_indata.h',
		'netinet/sctp_input.h',
		'netinet/sctp_lock_bsd.h',
		'netinet/sctp_os_bsd.h',
		'netinet/sctp_os.h',
		'netinet/sctp_output.h',
		'netinet/sctp_pcb.h',
		'netinet/sctp_peeloff.h',
		'netinet/sctp_structs.h',
		'netinet/sctp_sysctl.h',
		'netinet/sctp_timer.h',
		'netinet/sctp_uio.h',
		'netinet/sctputil.h',
		'netinet/sctp_var.h',
		'netinet/tcp_debug.h',
		'netinet/tcp_fsm.h',
		'netinet/tcp.h',
		'netinet/tcp_hostcache.h',
		'netinet/tcpip.h',
		'netinet/tcp_lro.h',
		'netinet/tcp_offload.h',
		'netinet/tcp_seq.h',
		'netinet/tcp_syncache.h',
		'netinet/tcp_timer.h',
		'netinet/tcp_var.h',
		'netinet/toedev.h',
		'netinet/udp.h',
		'netinet/udp_var.h',
		'netinet/libalias/alias_local.h',
		'netinet/libalias/alias.h',
		'netinet/libalias/alias_mod.h',
		'netinet/libalias/alias_sctp.h',
	]
)
# in_cksum.c is architecture dependent
netinet.addSourceFiles(
	[
		'netinet/accf_data.c',
		'netinet/accf_dns.c',
		'netinet/accf_http.c',
		'netinet/if_atm.c',
		'netinet/if_ether.c',
		'netinet/igmp.c',
		'netinet/in.c',
		'netinet/in_gif.c',
		'netinet/in_mcast.c',
		'netinet/in_pcb.c',
		'netinet/in_proto.c',
		'netinet/in_rmx.c',
		'netinet/ip_carp.c',
		'netinet/ip_divert.c',
		'netinet/ip_ecn.c',
		'netinet/ip_encap.c',
		'netinet/ip_fastfwd.c',
		'netinet/ip_gre.c',
		'netinet/ip_icmp.c',
		'netinet/ip_id.c',
		'netinet/ip_input.c',
		'netinet/ip_ipsec.c',
		'netinet/ip_mroute.c',
		'netinet/ip_options.c',
		'netinet/ip_output.c',
		'netinet/raw_ip.c',
		'netinet/sctp_asconf.c',
		'netinet/sctp_auth.c',
		'netinet/sctp_bsd_addr.c',
		'netinet/sctp_cc_functions.c',
		'netinet/sctp_crc32.c',
		'netinet/sctp_indata.c',
		'netinet/sctp_input.c',
		'netinet/sctp_output.c',
		'netinet/sctp_pcb.c',
		'netinet/sctp_peeloff.c',
		'netinet/sctp_sysctl.c',
		'netinet/sctp_timer.c',
		'netinet/sctp_usrreq.c',
		'netinet/sctputil.c',
		'netinet/tcp_debug.c',
		#'netinet/tcp_hostcache.c',
		'netinet/tcp_input.c',
		'netinet/tcp_lro.c',
		'netinet/tcp_offload.c',
		'netinet/tcp_output.c',
		'netinet/tcp_reass.c',
		'netinet/tcp_sack.c',
		'netinet/tcp_subr.c',
		'netinet/tcp_syncache.c',
		'netinet/tcp_timer.c',
		'netinet/tcp_timewait.c',
		'netinet/tcp_usrreq.c',
		'netinet/udp_usrreq.c',
		'netinet/ipfw/dn_sched_fifo.c',
		'netinet/ipfw/dn_sched_rr.c',
		'netinet/ipfw/ip_fw_log.c',
		'netinet/ipfw/dn_sched_qfq.c',
		'netinet/ipfw/dn_sched_prio.c',
		#'netinet/ipfw/ip_fw_dynamic.c',
		'netinet/ipfw/ip_dn_glue.c',
		'netinet/ipfw/ip_fw2.c',
		'netinet/ipfw/dn_heap.c',
		'netinet/ipfw/ip_dummynet.c',
		'netinet/ipfw/ip_fw_sockopt.c',
		'netinet/ipfw/dn_sched_wf2q.c',
		'netinet/ipfw/ip_fw_nat.c',
		'netinet/ipfw/ip_fw_pfil.c',
		'netinet/ipfw/ip_dn_io.c',
		'netinet/ipfw/ip_fw_table.c',
		'netinet/libalias/alias_dummy.c',
		'netinet/libalias/alias_pptp.c',
		'netinet/libalias/alias_smedia.c',
		'netinet/libalias/alias_mod.c',
		'netinet/libalias/alias_cuseeme.c',
		'netinet/libalias/alias_nbt.c',
		'netinet/libalias/alias_irc.c',
		'netinet/libalias/alias_util.c',
		'netinet/libalias/alias_db.c',
		'netinet/libalias/alias_ftp.c',
		'netinet/libalias/alias_proxy.c',
		'netinet/libalias/alias.c',
		'netinet/libalias/alias_skinny.c',
		'netinet/libalias/alias_sctp.c',
	]
)

netinet6 = Module('netinet6')
netinet6.conditionalOn = "DISABLE_IPV6"
netinet6.cppPattern = 's/^\#define INET6 1/\/\/ \#define INET6 1/'
netinet6.addHeaderFiles(
	[
		'netinet6/icmp6.h',
		'netinet6/in6_gif.h',
		'netinet6/in6.h',
		'netinet6/in6_ifattach.h',
		'netinet6/in6_pcb.h',
		'netinet6/in6_var.h',
		'netinet6/ip6_ecn.h',
		'netinet6/ip6.h',
		'netinet6/ip6_ipsec.h',
		'netinet6/ip6_mroute.h',
		'netinet6/ip6protosw.h',
		'netinet6/ip6_var.h',
		'netinet6/mld6.h',
		'netinet6/mld6_var.h',
		'netinet6/nd6.h',
		'netinet6/pim6.h',
		'netinet6/pim6_var.h',
		'netinet6/raw_ip6.h',
		'netinet6/scope6_var.h',
		'netinet6/sctp6_var.h',
		'netinet6/tcp6_var.h',
		'netinet6/udp6_var.h',
	]
)
netinet6.addSourceFiles(
	[
		'net/if_stf.c',
		'netinet6/dest6.c',
		'netinet6/frag6.c',
		'netinet6/icmp6.c',
		'netinet6/in6.c',
		'netinet6/in6_cksum.c',
		'netinet6/in6_gif.c',
		'netinet6/in6_ifattach.c',
		'netinet6/in6_mcast.c',
		'netinet6/in6_pcb.c',
		'netinet6/in6_proto.c',
		'netinet6/in6_rmx.c',
		'netinet6/in6_src.c',
		'netinet6/ip6_forward.c',
		'netinet6/ip6_id.c',
		'netinet6/ip6_input.c',
		'netinet6/ip6_ipsec.c',
		'netinet6/ip6_mroute.c',
		'netinet6/ip6_output.c',
		'netinet6/mld6.c',
		'netinet6/nd6.c',
		'netinet6/nd6_nbr.c',
		'netinet6/nd6_rtr.c',
		'netinet6/raw_ip6.c',
		'netinet6/route6.c',
		'netinet6/scope6.c',
		'netinet6/sctp6_usrreq.c',
		'netinet6/udp6_usrreq.c',
	]
)

netipsec = Module('netipsec')
netipsec.addHeaderFiles(
	[
		'netipsec/ah.h',
		'netipsec/ah_var.h',
		'netipsec/esp.h',
		'netipsec/esp_var.h',
		'netipsec/ipcomp.h',
		'netipsec/ipcomp_var.h',
		'netipsec/ipip_var.h',
		'netipsec/ipsec6.h',
		'netipsec/ipsec.h',
		'netipsec/keydb.h',
		'netipsec/key_debug.h',
		'netipsec/key.h',
		'netipsec/keysock.h',
		'netipsec/key_var.h',
		'netipsec/xform.h',
	]
)
netipsec.addSourceFiles(
	[
		'netipsec/ipsec.c',
		'netipsec/ipsec_input.c',
		'netipsec/ipsec_mbuf.c',
		'netipsec/ipsec_output.c',
		'netipsec/key.c',
		'netipsec/key_debug.c',
		'netipsec/keysock.c',
		'netipsec/xform_ah.c',
		'netipsec/xform_esp.c',
		'netipsec/xform_ipcomp.c',
		'netipsec/xform_ipip.c',
		'netipsec/xform_tcp.c',
	]
)

net80211 = Module('net80211')
net80211.addHeaderFiles(
	[
		'net80211/ieee80211_action.h',
		'net80211/ieee80211_adhoc.h',
		'net80211/ieee80211_ageq.h',
		'net80211/ieee80211_amrr.h',
		'net80211/ieee80211_crypto.h',
		'net80211/ieee80211_dfs.h',
		'net80211/ieee80211_freebsd.h',
		'net80211/_ieee80211.h',
		'net80211/ieee80211.h',
		'net80211/ieee80211_hostap.h',
		'net80211/ieee80211_ht.h',
		'net80211/ieee80211_input.h',
		'net80211/ieee80211_ioctl.h',
		'net80211/ieee80211_mesh.h',
		'net80211/ieee80211_monitor.h',
		'net80211/ieee80211_node.h',
		'net80211/ieee80211_phy.h',
		'net80211/ieee80211_power.h',
		'net80211/ieee80211_proto.h',
		'net80211/ieee80211_radiotap.h',
		'net80211/ieee80211_ratectl.h',
		'net80211/ieee80211_regdomain.h',
		'net80211/ieee80211_rssadapt.h',
		'net80211/ieee80211_scan.h',
		'net80211/ieee80211_sta.h',
		'net80211/ieee80211_superg.h',
		'net80211/ieee80211_tdma.h',
		'net80211/ieee80211_var.h',
		'net80211/ieee80211_wds.h',
	]
)
netipsec.addSourceFiles(
	[
		'net80211/ieee80211_acl.c',
		'net80211/ieee80211_action.c',
		'net80211/ieee80211_adhoc.c',
		'net80211/ieee80211_ageq.c',
		'net80211/ieee80211_amrr.c',
		'net80211/ieee80211.c',
		'net80211/ieee80211_crypto.c',
		'net80211/ieee80211_crypto_ccmp.c',
		'net80211/ieee80211_crypto_none.c',
		'net80211/ieee80211_crypto_tkip.c',
		'net80211/ieee80211_crypto_wep.c',
		'net80211/ieee80211_ddb.c',
		'net80211/ieee80211_dfs.c',
		'net80211/ieee80211_freebsd.c',
		'net80211/ieee80211_hostap.c',
		'net80211/ieee80211_ht.c',
		'net80211/ieee80211_hwmp.c',
		'net80211/ieee80211_input.c',
		'net80211/ieee80211_ioctl.c',
		'net80211/ieee80211_mesh.c',
		'net80211/ieee80211_monitor.c',
		'net80211/ieee80211_node.c',
		'net80211/ieee80211_output.c',
		'net80211/ieee80211_phy.c',
		'net80211/ieee80211_power.c',
		'net80211/ieee80211_proto.c',
		'net80211/ieee80211_radiotap.c',
		'net80211/ieee80211_ratectl.c',
		'net80211/ieee80211_ratectl_none.c',
		'net80211/ieee80211_regdomain.c',
		'net80211/ieee80211_rssadapt.c',
		'net80211/ieee80211_scan.c',
		'net80211/ieee80211_scan_sta.c',
		'net80211/ieee80211_sta.c',
		'net80211/ieee80211_superg.c',
		'net80211/ieee80211_tdma.c',
		'net80211/ieee80211_wds.c',
		'net80211/ieee80211_xauth.c',
	]
)

opencrypto = Module('opencrypto')
opencrypto.addHeaderFiles(
	[
		'sys/md5.h',
		'opencrypto/deflate.h',
		'opencrypto/xform.h',
		'opencrypto/cryptosoft.h',
		'opencrypto/rmd160.h',
		'opencrypto/cryptodev.h',
		'opencrypto/castsb.h',
		'opencrypto/skipjack.h',
		'opencrypto/cast.h',
	]
)
opencrypto.addSourceFiles(
	[
		'opencrypto/crypto.c',
		'opencrypto/deflate.c',
		'opencrypto/cryptosoft.c',
		'opencrypto/criov.c',
		'opencrypto/rmd160.c',
		'opencrypto/xform.c',
		'opencrypto/skipjack.c',
		'opencrypto/cast.c',
		'opencrypto/cryptodev.c',
	]
)

crypto = Module('crypto')
crypto.addHeaderFiles(
	[
		#'crypto/aesni/aesni.h',
		'crypto/sha1.h',
		'crypto/sha2/sha2.h',
		'crypto/rijndael/rijndael.h',
		'crypto/rijndael/rijndael_local.h',
		'crypto/rijndael/rijndael-api-fst.h',
		'crypto/des/des.h',
		'crypto/des/spr.h',
		'crypto/des/podd.h',
		'crypto/des/sk.h',
		'crypto/des/des_locl.h',
		'crypto/blowfish/bf_pi.h',
		'crypto/blowfish/bf_locl.h',
		'crypto/blowfish/blowfish.h',
		'crypto/rc4/rc4.h',
		#'crypto/via/padlock.h',
		'crypto/camellia/camellia.h',
	]
)
crypto.addSourceFiles(
	[
		#'crypto/aesni/aesni.c',
		#'crypto/aesni/aesni_wrap.c',
		'crypto/sha1.c',
		'crypto/sha2/sha2.c',
		'crypto/rijndael/rijndael-alg-fst.c',
		'crypto/rijndael/rijndael-api.c',
		'crypto/rijndael/rijndael-api-fst.c',
		'crypto/des/des_setkey.c',
		'crypto/des/des_enc.c',
		'crypto/des/des_ecb.c',
		'crypto/blowfish/bf_enc.c',
		'crypto/blowfish/bf_skey.c',
		'crypto/blowfish/bf_ecb.c',
		'crypto/rc4/rc4.c',
		#'crypto/via/padlock.c',
		#'crypto/via/padlock_cipher.c',
		#'crypto/via/padlock_hash.c',
		'crypto/camellia/camellia-api.c',
		'crypto/camellia/camellia.c',
	]
)

altq = Module('altq')
altq.addHeaderFiles(
	[
		'contrib/altq/altq/altq_rmclass.h',
		'contrib/altq/altq/altq_cbq.h',
		'contrib/altq/altq/altq_var.h',
		'contrib/altq/altq/altqconf.h',
		'contrib/altq/altq/altq.h',
		'contrib/altq/altq/altq_hfsc.h',
		'contrib/altq/altq/altq_red.h',
		'contrib/altq/altq/altq_classq.h',
		'contrib/altq/altq/altq_priq.h',
		'contrib/altq/altq/altq_rmclass_debug.h',
		'contrib/altq/altq/altq_cdnr.h',
		'contrib/altq/altq/altq_rio.h',
		'contrib/altq/altq/if_altq.h',
	]
)
altq.addSourceFiles(
	[
		'contrib/altq/altq/altq_rmclass.c',
		'contrib/altq/altq/altq_rio.c',
		'contrib/altq/altq/altq_subr.c',
		'contrib/altq/altq/altq_cdnr.c',
		'contrib/altq/altq/altq_priq.c',
		'contrib/altq/altq/altq_cbq.c',
		'contrib/altq/altq/altq_hfsc.c',
		'contrib/altq/altq/altq_red.c',
	]
)

# contrib/pf Module
pf = Module('pf')
pf.addHeaderFiles(
	[
		'contrib/pf/net/pf_mtag.h',
		'contrib/pf/net/if_pfsync.h',
		'contrib/pf/net/pfvar.h',
		'contrib/pf/net/if_pflog.h',
	]
)
pf.addSourceFiles(
	[
		'contrib/pf/netinet/in4_cksum.c',
		'contrib/pf/net/pf.c',
		'contrib/pf/net/if_pflog.c',
		'contrib/pf/net/pf_subr.c',
		'contrib/pf/net/pf_ioctl.c',
		'contrib/pf/net/pf_table.c',
		'contrib/pf/net/pf_if.c',
		'contrib/pf/net/pf_osfp.c',
		'contrib/pf/net/pf_norm.c',
		'contrib/pf/net/pf_ruleset.c',
		'contrib/pf/net/if_pfsync.c',
	]
)

# in_chksum Module
in_cksum = Module('in_cksum')
in_cksum.addRTEMSHeaderFiles(
	[
        ]
)
in_cksum.addCPUDependentHeaderFiles(
	[
		'arm/include/in_cksum.h',
		'i386/include/in_cksum.h',
		'mips/include/in_cksum.h',
		'powerpc/include/in_cksum.h',
		'sparc64/include/in_cksum.h',
	]
)
in_cksum.addCPUDependentSourceFiles(
	'arm',
	[
		'arm/arm/in_cksum.c',
	]
)
in_cksum.addCPUDependentSourceFiles(
	'i386',
	[
		'i386/i386/in_cksum.c',
	]
)
in_cksum.addCPUDependentSourceFiles(
	'mips',
	[
		'mips/mips/in_cksum.c',
	]
)
in_cksum.addCPUDependentSourceFiles(
	'powerpc',
	[
		'powerpc/powerpc/in_cksum.c',
	]
)
in_cksum.addCPUDependentSourceFiles(
	'sparc',
	[
		'mips/mips/in_cksum.c',
	]
)
in_cksum.addCPUDependentSourceFiles(
	'sparc64',
	[
		'sparc64/sparc64/in_cksum.c',
	]
)

# Register all the Module instances with the Module Manager
mm.addModule(rtems)
mm.addModule(netDeps)
mm.addModule(net)
mm.addModule(netinet)
mm.addModule(netinet6)
mm.addModule(netipsec)
mm.addModule(net80211)
mm.addModule(opencrypto)
mm.addModule(crypto)
mm.addModule(altq)
mm.addModule(pf)
mm.addModule(devNet)

mm.addModule(local)
mm.addModule(devUsbBase)
mm.addModule(devUsb)
mm.addModule(devUsbQuirk)
mm.addModule(devUsbController)

mm.addModule(cam)
mm.addModule(devUsbStorage)
#mm.addModule(devUsbNet)

# Add PCI
mm.addModule(devPci)

# Add NIC devices
mm.addModule(devNic)
mm.addModule(devNic_re)
mm.addModule(devNic_fxp)
mm.addModule(devNic_e1000)
mm.addModule(devNic_dc)
mm.addModule(devNic_smc)
mm.addModule(devNic_broadcomm)
# TBD Requires ISA and PCCard Support to be pulled in.
# mm.addModule(devNic_cs)

# Add in_chksum
mm.addModule(in_cksum)

# XXX TODO Check that no file is also listed in empty
# XXX TODO Check that no file in in two modules

# Perform the actual file manipulation
if isForward == True:
  if isOnlyMakefile == False:
    mm.copyFromFreeBSDToRTEMS()
  mm.createMakefile()
else:
  mm.copyFromRTEMSToFreeBSD()

# Print a summary if changing files
if isDiffMode == False:
  if filesProcessed == 1:
    print str(filesProcessed) + " file was changed."
  else:
    print str(filesProcessed) + " files were changed."
