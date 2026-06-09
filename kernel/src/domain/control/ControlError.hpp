#pragma once

#include <string>

namespace dietcode::domain::control {

struct ControlError {
    static inline const std::string InvalidRequest = "invalid_request";
    static inline const std::string InvalidParams = "invalid_params";
    static inline const std::string PermissionDenied = "permission_denied";
    static inline const std::string MethodNotFound = "method_not_found";
    static inline const std::string InternalError = "internal_error";
    static inline const std::string NotFound = "not_found";
    static inline const std::string AlreadyExists = "already_exists";
    static inline const std::string FileTooLarge = "file_too_large";
    static inline const std::string ResponseTooLarge = "response_too_large";
    static inline const std::string ResourceExhausted = "resource_exhausted";
    static inline const std::string OutsideWorkspace = "outside_workspace";
    static inline const std::string PatchFailed = "patch_failed";
    static inline const std::string StaleContent = "stale_content";
    static inline const std::string ConfirmationRequired = "confirmation_required";
    static inline const std::string LockConflict = "lock_conflict";
    static inline const std::string CheckpointWriteFailed = "checkpoint_write_failed";
    static inline const std::string RollbackFailed = "rollback_failed";
    static inline const std::string BackupManifestMissing = "backup_manifest_missing";
    static inline const std::string BackupManifestInvalid = "backup_manifest_invalid";
    static inline const std::string BackupCorrupt = "backup_corrupt";
};

} // namespace dietcode::domain::control
