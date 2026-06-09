#import <Cocoa/Cocoa.h>

#include "domain/control/ControlReleaseVersions.hpp"

NSDictionary* MacControlContractVersionsDictionary(void) {
    using dietcode::domain::control::kContractInventoryVersion;
    using dietcode::domain::control::kControlProtocolVersion;
    using dietcode::domain::control::kDiagnosticsSchemaVersion;
    using dietcode::domain::control::kErrorTaxonomyVersion;
    using dietcode::domain::control::kHarnessSummarySchemaVersion;
    using dietcode::domain::control::kRpcEnvelopeSchemaVersion;
    using dietcode::domain::control::kSafetyLimitsSchemaVersion;
    using dietcode::domain::control::kTransactionSchemaVersion;

    return @{
        @"controlProtocol": @(kControlProtocolVersion),
        @"transactionSchema": @(kTransactionSchemaVersion),
        @"contractInventory": @(kContractInventoryVersion),
        @"rpcEnvelope": @(kRpcEnvelopeSchemaVersion),
        @"errorTaxonomy": @(kErrorTaxonomyVersion),
        @"diagnostics": @(kDiagnosticsSchemaVersion),
        @"safetyLimits": @(kSafetyLimitsSchemaVersion),
        @"harnessSummary": @(kHarnessSummarySchemaVersion),
    };
}
