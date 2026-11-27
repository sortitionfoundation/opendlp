"""ABOUTME: In-memory repository fakes that implement the same interfaces as the SQL ones
ABOUTME: Re-exports every repository fake so callers can import from tests.fakes.repositories"""

from tests.fakes.repositories.assemblies import (
    FakeAssemblyExportGSheetRepository,
    FakeAssemblyGSheetRepository,
    FakeAssemblyRepository,
    FakeSelectionRunRecordRepository,
    FakeTargetCategoryRepository,
)
from tests.fakes.repositories.base import FakeRepository
from tests.fakes.repositories.registration import (
    FakeEmailTemplateRepository,
    FakeRegistrationContentBlockRepository,
    FakeRegistrationDocumentRepository,
    FakeRegistrationImageRepository,
    FakeRegistrationPageHtmlRepository,
    FakeRegistrationPageRepository,
    FakeRespondentEmailSendRecordRepository,
)
from tests.fakes.repositories.respondents import (
    FakeRespondentFieldDefinitionRepository,
    FakeRespondentFieldMappingEntryRepository,
    FakeRespondentRepository,
)
from tests.fakes.repositories.users import (
    FakeEmailConfirmationTokenRepository,
    FakePasswordResetTokenRepository,
    FakeTotpVerificationAttemptRepository,
    FakeTwoFactorAuditLogRepository,
    FakeUserAssemblyRoleRepository,
    FakeUserBackupCodeRepository,
    FakeUserInviteRepository,
    FakeUserRepository,
    FakeUserSignupSurveyRepository,
)

__all__ = [
    "FakeAssemblyExportGSheetRepository",
    "FakeAssemblyGSheetRepository",
    "FakeAssemblyRepository",
    "FakeEmailConfirmationTokenRepository",
    "FakeEmailTemplateRepository",
    "FakePasswordResetTokenRepository",
    "FakeRegistrationContentBlockRepository",
    "FakeRegistrationDocumentRepository",
    "FakeRegistrationImageRepository",
    "FakeRegistrationPageHtmlRepository",
    "FakeRegistrationPageRepository",
    "FakeRepository",
    "FakeRespondentEmailSendRecordRepository",
    "FakeRespondentFieldDefinitionRepository",
    "FakeRespondentFieldMappingEntryRepository",
    "FakeRespondentRepository",
    "FakeSelectionRunRecordRepository",
    "FakeTargetCategoryRepository",
    "FakeTotpVerificationAttemptRepository",
    "FakeTwoFactorAuditLogRepository",
    "FakeUserAssemblyRoleRepository",
    "FakeUserBackupCodeRepository",
    "FakeUserInviteRepository",
    "FakeUserRepository",
    "FakeUserSignupSurveyRepository",
]
