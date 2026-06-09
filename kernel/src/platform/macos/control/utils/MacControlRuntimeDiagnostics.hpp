#pragma once

#import <Cocoa/Cocoa.h>

namespace dietcode::platform::macos {

// CONTRACT: NDJSON runtime diagnostic line schema (grep: rg 'runtime_diagnostic' src/ docs/).
// Required keys: type, timestamp, request_id, method, phase, ok
// Optional keys: string_code, queue, duration_ms

NSString* MacControlRuntimeDiagnosticLogPath(void);
NSDictionary* MacControlRpcErrorDiagnosticMetadata(NSString* stringCode);
void MacControlAppendRuntimeDiagnosticLine(NSDictionary* fields);

} // namespace dietcode::platform::macos
