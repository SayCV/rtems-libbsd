# Define your CPU here:
CPU=arm
#CPU=i386
#CPU=ppc
#CPU=m68k
#CPU=h8300

# Define the location of the rtem installation:
RTEMS_VER=4.11
RTEMS_BASE=/opt/rtems-$(RTEMS_VER)

# Define the object module format here:
OMF=elf
#OMF=aout
#OMF=coff

# Define the board support package here:
BSP=SayCV_SAM9X25

#RTEMS_MAKEFILE_PATH = ${HOME}/newbsd/bsp-install/powerpc-rtems4.11/psim/
#INSTALL_BASE = ${HOME}/newbsd/install
RTEMS_MAKEFILE_PATH=$(RTEMS_BASE)/$(CPU)-rtemseabi$(RTEMS_VER)/$(BSP)
INSTALL_BASE = /opt/rtems-$(RTEMS_VER)-demos

DISABLE_IPV6=yes