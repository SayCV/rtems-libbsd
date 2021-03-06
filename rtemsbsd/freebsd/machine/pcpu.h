/**
 * @file
 *
 * @ingroup rtems_bsd_machine
 *
 * @brief TODO.
 */

/*
 * Copyright (c) 2009, 2010 embedded brains GmbH.  All rights reserved.
 *
 *  embedded brains GmbH
 *  Obere Lagerstr. 30
 *  82178 Puchheim
 *  Germany
 *  <rtems@embedded-brains.de>
 *
 * The license and distribution terms for this file may be
 * found in the file LICENSE in this distribution or at
 * http://www.rtems.com/license/LICENSE.
 */

#ifndef _RTEMS_BSD_MACHINE_PCPU_H_
#define _RTEMS_BSD_MACHINE_PCPU_H_

#ifndef _RTEMS_BSD_MACHINE_RTEMS_BSD_CONFIG_H_
#error "the header file <freebsd/machine/rtems-bsd-config.h> must be included first"
#endif

#define curthread (( struct thread * )(( RTEMS_API_Control * )_Thread_Executing->API_Extensions[THREAD_API_RTEMS] )->Notepads[RTEMS_NOTEPAD_0] )

extern struct pcpu *pcpup;

#define PCPU_MD_FIELDS
#define PCPU_GET(member) (0)
#define PCPU_SET(member, val)

//#define PCPU_GET(member)  (pcpup->pc_ ## member)
//#define PCPU_SET(member, val) (pcpup->pc_ ## member = (val))

#endif /* _RTEMS_BSD_MACHINE_PCPU_H_ */
