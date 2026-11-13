"""Every detector Operon ships. Add a detector here; its rule id and version are part of the
insight record, so a changed calculation needs a new version, not an edit in place."""

from operon.modules.intelligence.detectors.base import Detector
from operon.modules.intelligence.detectors.po_overdue import PurchaseOrderOverdueDetector
from operon.modules.intelligence.detectors.stockout import StockoutRiskDetector

DETECTORS: dict[str, Detector] = {
    d.rule_id: d for d in (StockoutRiskDetector(), PurchaseOrderOverdueDetector())
}
