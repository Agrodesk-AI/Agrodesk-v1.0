from app.models.base import Base
from app.models.consent import Consent
from app.models.customer import Customer
from app.models.dealer import Dealer
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.otp import OtpCode
from app.models.task import Task
from app.models.user import User

__all__ = [
    "Base",
    "Consent",
    "Customer",
    "Dealer",
    "Lead",
    "LeadEvent",
    "OtpCode",
    "Task",
    "User",
]
