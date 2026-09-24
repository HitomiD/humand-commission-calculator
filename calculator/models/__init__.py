"""Domain models, split by layer. Import from here: ``from calculator.models import Deal``."""

from calculator.models.inputs import ApprovedPayment, Deal, Payment, PaymentTerm
from calculator.models.llm import ExtractedFee, ExtractedTier, RuleExtraction
from calculator.models.output import CommissionLine, Estado, PartnerTransfer, TierSlice, Trace
from calculator.models.rules import CommissionRule, FeeDeduction, Tier, tier_issues

__all__ = [
    "ApprovedPayment", "CommissionLine", "CommissionRule", "Deal", "Estado", "ExtractedFee",
    "ExtractedTier", "FeeDeduction", "PartnerTransfer", "Payment", "PaymentTerm", "RuleExtraction", "Tier",
    "TierSlice", "Trace", "tier_issues",
]
