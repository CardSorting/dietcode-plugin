#pragma once

#import <Foundation/Foundation.h>

// CONTRACT: Agent-safe tool registry for deterministic retrieval surfaces.
NSDictionary* MacControlToolRegistryPayload(void);
NSDictionary* MacControlToolCapabilitiesSummary(void);
NSDictionary* MacControlToolEntryForMethod(NSString* method);
