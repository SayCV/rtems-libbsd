/**
 * @file
 *
 * @ingroup rtems_bsd_rtems
 *
 * @brief TODO.
 *
 * File origin from FreeBSD 'lib/libc/gen/sysctlbyname.c'.
 */

/*
 * ----------------------------------------------------------------------------
 * "THE BEER-WARE LICENSE" (Revision 42):
 * <phk@FreeBSD.org> wrote this file.  As long as you retain this notice you
 * can do whatever you want with this stuff. If we meet some day, and you think
 * this stuff is worth it, you can buy me a beer in return.   Poul-Henning Kamp
 * ----------------------------------------------------------------------------
 *
 */

#include <freebsd/machine/rtems-bsd-config.h>

#include <freebsd/sys/cdefs.h>
__FBSDID("$FreeBSD$");

#include <freebsd/sys/types.h>
#include <freebsd/sys/sysctl.h>

int
sysctlbyname(const char *name, void *oldp, size_t *oldlenp,
    void *newp, size_t newlen)
{
	int real_oid[CTL_MAXNAME+2];
	int error;
	size_t oidlen;

	oidlen = sizeof(real_oid) / sizeof(int);
	error = sysctlnametomib(name, real_oid, &oidlen);
	if (error < 0)
		return (error);
	error = sysctl(real_oid, oidlen, oldp, oldlenp, newp, newlen);
	return (error);
}
