"""Shared generation errors; safe messages only, without provider payloads or secrets."""
class GenerationError(Exception):pass
class TransientGenerationError(GenerationError):pass
class RejectedGenerationError(GenerationError):pass
class RateLimitedGenerationError(RejectedGenerationError,TransientGenerationError):pass
class PendingBatch(Exception):pass
class Cancelled(Exception):pass
