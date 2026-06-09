#pragma once

#import <Cocoa/Cocoa.h>

namespace dietcode::platform::macos {

NSString* ISODateString(NSDate* date);
NSString* StableHashForData(NSData* data);
NSString* StableHashForString(NSString* text);
NSString* SHA256ForData(NSData* data);
NSString* RequestIdString(id value);
NSString* MacControlCanonicalJsonString(id obj, NSString** errorOut);
NSDictionary* MacControlJsonSanitizedDictionary(id value, NSError** errorOut);

} // namespace dietcode::platform::macos
