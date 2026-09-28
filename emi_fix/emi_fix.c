// SPDX-License-Identifier: GPL-2.0
/*
 * emi_fix - 为 WiFi(CONSYS) 子系统配置 EMI MPU 访问权限
 *
 * 背景：公开树缺少 conninfra 的 mt6833 平台代码，芯片的 EMI MPU 配置缺失，
 *       导致 WiFi 固件下载时被 MPU 拒绝（emimpu_violation_irq: violation at emi0）。
 *       内核已导出 emi_mpu_set_protection()，此处直接调用补上。
 *
 * 所有关键值都是模块参数 → 一次编译可试多种配置，无需反复重建。
 * 用法示例：
 *   insmod emi_fix.ko region=15 start=0x0 size=0x0 apc=0     # 全放行
 *   insmod emi_fix.ko region=8  apc=0x00000000000000000000    # 指定槽位
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>

/* ---- 与内核 drivers/misc/mediatek/emi/submodule/mpu_v1.h 保持一致 ---- */
#define EMI_FIX_DGROUP_MAX 8          /* 上限，内核只读它自己的组数，给大更安全 */
struct emi_region_info_t {
	unsigned long long start;
	unsigned long long end;
	unsigned int region;
	unsigned int apc[EMI_FIX_DGROUP_MAX];
};
extern int emi_mpu_set_protection(struct emi_region_info_t *region_info);

/* ---- wmt_drv 导出的 CONSYS EMI 基址/大小 ---- */
extern unsigned long long gConEmiPhyBase;
extern unsigned long long gConEmiSize;

static int region = 15;
module_param(region, int, 0644);
MODULE_PARM_DESC(region, "EMI MPU region slot (0-31)");

static unsigned long long start;
module_param(start, ullong, 0644);
MODULE_PARM_DESC(start, "region start (0 = use gConEmiPhyBase)");

static unsigned long long size;
module_param(size, ullong, 0644);
MODULE_PARM_DESC(size, "region size (0 = use gConEmiSize)");

static ulong apc0 = 0;
module_param(apc0, ulong, 0644);
MODULE_PARM_DESC(apc0, "apc[0] value (0 = all domains NO_PROTECTION)");

static ulong apc1 = 0;
module_param(apc1, ulong, 0644);
MODULE_PARM_DESC(apc1, "apc[1] value");

static int dry_run;
module_param(dry_run, int, 0644);
MODULE_PARM_DESC(dry_run, "1 = only print, do not touch MPU");

static int __init emi_fix_init(void)
{
	struct emi_region_info_t r;
	unsigned long long b = start, s = size;
	int i, ret;

	if (!b || !s) {
		b = gConEmiPhyBase;
		s = gConEmiSize;
	}
	memset(&r, 0, sizeof(r));
	r.region = (unsigned int)region;
	r.start = b;
	r.end = (s ? (b + s - 1) : b);
	r.apc[0] = (unsigned int)apc0;
	r.apc[1] = (unsigned int)apc1;

	pr_info("[emi_fix] region=%d start=0x%llx end=0x%llx apc[0]=0x%x apc[1]=0x%x dry=%d\n",
		r.region, r.start, r.end, r.apc[0], r.apc[1], dry_run);
	pr_info("[emi_fix] CONSYS EMI base=0x%llx size=0x%llx\n", gConEmiPhyBase, gConEmiSize);
	for (i = 0; i < 2; i++)
		pr_info("[emi_fix] apc[%d]=0x%08x\n", i, r.apc[i]);

	if (dry_run) {
		pr_info("[emi_fix] dry_run, skip emi_mpu_set_protection\n");
		return 0;
	}
	ret = emi_mpu_set_protection(&r);
	pr_info("[emi_fix] emi_mpu_set_protection ret=%d\n", ret);
	return 0;   /* 失败也不卸载，方便观察 */
}

static void __exit emi_fix_exit(void)
{
	pr_info("[emi_fix] unloaded\n");
}

module_init(emi_fix_init);
module_exit(emi_fix_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Configure EMI MPU access for WiFi/CONSYS");
