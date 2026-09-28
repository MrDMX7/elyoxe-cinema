"""site_kit.Kit's helpers split by what they draw (W1-P1, MASTER-PLAN §5.2): media, tile, sched, ticket, chrome,
filters. Each module is a mixin of site_kit.Kit and one Wave 2 owner's file (§6.2). Page modules import
site_kit, never these: site_kit imports them once its helpers exist, and importing it first keeps that order."""
import site_kit  # noqa: F401,E402
