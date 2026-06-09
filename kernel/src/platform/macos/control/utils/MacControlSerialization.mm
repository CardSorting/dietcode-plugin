#import "MacControlSerialization.hpp"
#import <CommonCrypto/CommonDigest.h>
#include <cstdint>

namespace dietcode::platform::macos {

NSString* ISODateString(NSDate* date) {
    if (!date) return @"";
    static NSDateFormatter* formatter = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        formatter = [[NSDateFormatter alloc] init];
        formatter.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
        formatter.timeZone = [NSTimeZone timeZoneForSecondsFromGMT:0];
        formatter.dateFormat = @"yyyy-MM-dd'T'HH:mm:ss'Z'";
    });
    @synchronized(formatter) {
        return [formatter stringFromDate:date];
    }
}

NSString* StableHashForData(NSData* data) {
    if (!data) data = [NSData data];
    const uint8_t* bytes = (const uint8_t*)data.bytes;
    uint64_t hash = 1469598103934665603ULL;
    for (NSUInteger i = 0; i < data.length; i++) {
        hash ^= bytes[i];
        hash *= 1099511628211ULL;
    }
    return [NSString stringWithFormat:@"%016llx", hash];
}

NSString* StableHashForString(NSString* text) {
    NSData* data = [(text ?: @"") dataUsingEncoding:NSUTF8StringEncoding] ?: [NSData data];
    return StableHashForData(data);
}

NSString* SHA256ForData(NSData* data) {
    if (!data) data = [NSData data];
    uint8_t hash[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, hash);
    NSMutableString* s = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
    for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) {
        [s appendFormat:@"%02x", hash[i]];
    }
    return s;
}

NSString* RequestIdString(id value) {
    if ([value isKindOfClass:[NSString class]]) return value;
    if ([value isKindOfClass:[NSNumber class]]) return [value stringValue];
    return @"unknown";
}

NSString* MacControlCanonicalJsonString(id obj, NSString** errorOut) {
    if ([obj isKindOfClass:[NSString class]]) {
        NSMutableString* s = [NSMutableString stringWithString:obj];
        [s replaceOccurrencesOfString:@"\\" withString:@"\\\\" options:0 range:NSMakeRange(0, s.length)];
        [s replaceOccurrencesOfString:@"\"" withString:@"\\\"" options:0 range:NSMakeRange(0, s.length)];
        [s replaceOccurrencesOfString:@"\n" withString:@"\\n" options:0 range:NSMakeRange(0, s.length)];
        [s replaceOccurrencesOfString:@"\r" withString:@"\\r" options:0 range:NSMakeRange(0, s.length)];
        [s replaceOccurrencesOfString:@"\t" withString:@"\\t" options:0 range:NSMakeRange(0, s.length)];
        return [NSString stringWithFormat:@"\"%@\"", s];
    } else if ([obj isKindOfClass:[NSNumber class]]) {
        if (obj == (id)kCFBooleanTrue) {
            return @"true";
        } else if (obj == (id)kCFBooleanFalse) {
            return @"false";
        }
        const char* type = [obj objCType];
        if (type && (type[0] == 'c' || type[0] == 'B')) {
            return [obj boolValue] ? @"true" : @"false";
        }
        return [obj stringValue];
    } else if ([obj isKindOfClass:[NSArray class]]) {
        NSMutableArray* parts = [NSMutableArray array];
        for (id child in obj) {
            NSString* childJson = MacControlCanonicalJsonString(child, errorOut);
            if (!childJson) return nil;
            [parts addObject:childJson];
        }
        return [NSString stringWithFormat:@"[%@]", [parts componentsJoinedByString:@","]];
    } else if ([obj isKindOfClass:[NSDictionary class]]) {
        NSArray* sortedKeys = [[obj allKeys] sortedArrayUsingSelector:@selector(compare:)];
        NSMutableArray* parts = [NSMutableArray array];
        for (NSString* key in sortedKeys) {
            id val = obj[key];
            NSString* valJson = MacControlCanonicalJsonString(val, errorOut);
            if (!valJson) return nil;
            [parts addObject:[NSString stringWithFormat:@"\"%@\":%@", key, valJson]];
        }
        return [NSString stringWithFormat:@"{%@}", [parts componentsJoinedByString:@","]];
    } else if (obj == [NSNull null] || obj == nil) {
        return @"null";
    } else {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Unsupported type for canonical JSON: %@", NSStringFromClass([obj class])];
        return nil;
    }
}

NSDictionary* MacControlJsonSanitizedDictionary(id value, NSError** errorOut) {
    if (!value) {
        return @{};
    }
    if (![NSJSONSerialization isValidJSONObject:value]) {
        if (errorOut) {
            *errorOut = [NSError errorWithDomain:@"MacControlSerialization"
                                            code:1
                                        userInfo:@{NSLocalizedDescriptionKey: @"Value is not JSON-serializable."}];
        }
        return nil;
    }
    NSData* data = [NSJSONSerialization dataWithJSONObject:value options:0 error:errorOut];
    if (!data) return nil;
    id decoded = [NSJSONSerialization JSONObjectWithData:data options:NSJSONReadingFragmentsAllowed error:errorOut];
    if (![decoded isKindOfClass:[NSDictionary class]]) {
        if (errorOut) {
            *errorOut = [NSError errorWithDomain:@"MacControlSerialization"
                                            code:2
                                        userInfo:@{NSLocalizedDescriptionKey: @"Sanitized JSON root must be an object."}];
        }
        return nil;
    }
    return decoded;
}

} // namespace dietcode::platform::macos
