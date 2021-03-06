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

#ifndef _RTEMS_BSD_MACHINE_RUNQ_H_
#define _RTEMS_BSD_MACHINE_RUNQ_H_

#ifndef _RTEMS_BSD_MACHINE_RTEMS_BSD_CONFIG_H_
#error "the header file <freebsd/machine/rtems-bsd-config.h> must be included first"
#endif

#define RQB_LEN 0
#define RQB_L2BPW 0
#define RQB_BPW 0

#define RQB_BIT(pri) 0
#define RQB_WORD(pri) 0

#define RQB_FFS(word) 0

typedef uintptr_t rqb_word_t;

#endif /* _RTEMS_BSD_MACHINE_RUNQ_H_ */
