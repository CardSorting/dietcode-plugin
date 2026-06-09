#import "MacControlRecoveryStore.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"

#include <filesystem>
#include <string>
#include <system_error>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>

using namespace dietcode::platform::macos;

@implementation MacControlRecoveryStore {
    DietCodeControlWindowBridge* _windowBridge;
}

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge {
    self = [super init];
    if (self) {
        _windowBridge = bridge;
    }
    return self;
}

- (BOOL)validateManifestStructure:(NSDictionary*)manifest error:(NSString**)errorOut {
    if (![manifest isKindOfClass:[NSDictionary class]]) {
        if (errorOut) *errorOut = @"Manifest is not a JSON object.";
        return NO;
    }
    
    NSSet* allowedTopLevel = [NSSet setWithArray:@[
        @"schemaVersion",
        @"comboId",
        @"createdAt",
        @"workspaceRootHash",
        @"chipVersions",
        @"files"
    ]];
    
    for (NSString* key in manifest.allKeys) {
        if (![allowedTopLevel containsObject:key]) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Manifest contains unknown top-level field: %@", key];
            return NO;
        }
    }
    
    NSString* schemaVersion = manifest[@"schemaVersion"];
    if (schemaVersion && ![schemaVersion isKindOfClass:[NSString class]]) {
        if (errorOut) *errorOut = @"schemaVersion must be a string.";
        return NO;
    }
    
    if (schemaVersion && ![schemaVersion isEqualToString:@"1.6.1"] && ![schemaVersion isEqualToString:@"1.6.2"]) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Unsupported schema version: %@", schemaVersion];
        return NO;
    }
    
    NSString* comboId = manifest[@"comboId"];
    if (comboId) {
        if (![comboId isKindOfClass:[NSString class]]) {
            if (errorOut) *errorOut = @"comboId must be a string.";
            return NO;
        }
        if (comboId.length > 128) {
            if (errorOut) *errorOut = @"comboId exceeds maximum allowed length of 128 characters.";
            return NO;
        }
    }
    
    NSString* createdAt = manifest[@"createdAt"];
    if (createdAt && ![createdAt isKindOfClass:[NSString class]]) {
        if (errorOut) *errorOut = @"createdAt must be a string.";
        return NO;
    }
    
    NSString* wsHash = manifest[@"workspaceRootHash"];
    if (wsHash && ![wsHash isKindOfClass:[NSString class]]) {
        if (errorOut) *errorOut = @"workspaceRootHash must be a string.";
        return NO;
    }
    
    NSArray* chipVersions = manifest[@"chipVersions"];
    if (chipVersions) {
        if (![chipVersions isKindOfClass:[NSArray class]]) {
            if (errorOut) *errorOut = @"chipVersions must be an array.";
            return NO;
        }
        if (chipVersions.count > 32) {
            if (errorOut) *errorOut = @"chipVersions exceeds maximum count of 32 items.";
            return NO;
        }
        for (id item in chipVersions) {
            if (![item isKindOfClass:[NSString class]]) {
                if (errorOut) *errorOut = @"All items in chipVersions must be strings.";
                return NO;
            }
        }
    }
    
    NSArray* files = manifest[@"files"];
    if (files) {
        if (![files isKindOfClass:[NSArray class]]) {
            if (errorOut) *errorOut = @"files must be an array.";
            return NO;
        }
        if (files.count > 256) {
            if (errorOut) *errorOut = @"files array exceeds maximum size of 256 entries.";
            return NO;
        }
    }
    
    NSSet* allowedFileKeys = [NSSet setWithArray:@[
        @"workspaceRelativePath",
        @"canonicalPathHash",
        @"domain",
        @"wasMissing",
        @"wasBinary",
        @"sizeBytes",
        @"newlineMode",
        @"preimageHash",
        @"expectedPostimageHash",
        @"backupBlobHash"
    ]];
    
    for (id fileEntry in files ?: @[]) {
        if (![fileEntry isKindOfClass:[NSDictionary class]]) {
            if (errorOut) *errorOut = @"Every entry in files must be a JSON object.";
            return NO;
        }
        
        NSDictionary* entry = (NSDictionary*)fileEntry;
        for (NSString* key in entry.allKeys) {
            if (![allowedFileKeys containsObject:key]) {
                if (errorOut) *errorOut = [NSString stringWithFormat:@"File entry contains unknown field: %@", key];
                return NO;
            }
        }
        
        NSString* relPath = entry[@"workspaceRelativePath"];
        if (relPath) {
            if (![relPath isKindOfClass:[NSString class]]) {
                if (errorOut) *errorOut = @"workspaceRelativePath must be a string.";
                return NO;
            }
            if (relPath.length > 4096) {
                if (errorOut) *errorOut = @"workspaceRelativePath exceeds maximum allowed length of 4096 characters.";
                return NO;
            }
        }
        
        NSString* cPathHash = entry[@"canonicalPathHash"];
        if (cPathHash && ![cPathHash isKindOfClass:[NSString class]]) {
            if (errorOut) *errorOut = @"canonicalPathHash must be a string.";
            return NO;
        }
        
        NSString* domain = entry[@"domain"];
        if (domain) {
            if (![domain isKindOfClass:[NSString class]]) {
                if (errorOut) *errorOut = @"domain must be a string.";
                return NO;
            }
            if (![domain isEqualToString:@"disk"] && ![domain isEqualToString:@"buffer"]) {
                if (errorOut) *errorOut = [NSString stringWithFormat:@"domain has invalid enum value: %@", domain];
                return NO;
            }
        }
        
        NSString* preimageHash = entry[@"preimageHash"];
        if (preimageHash && ![preimageHash isKindOfClass:[NSString class]]) {
            if (errorOut) *errorOut = @"preimageHash must be a string.";
            return NO;
        }
        
        NSString* expPostHash = entry[@"expectedPostimageHash"];
        if (expPostHash && ![expPostHash isKindOfClass:[NSString class]]) {
            if (errorOut) *errorOut = @"expectedPostimageHash must be a string.";
            return NO;
        }
        
        NSString* backupBlobHash = entry[@"backupBlobHash"];
        if (backupBlobHash && ![backupBlobHash isKindOfClass:[NSString class]]) {
            if (errorOut) *errorOut = @"backupBlobHash must be a string.";
            return NO;
        }
        
        NSNumber* sizeBytes = entry[@"sizeBytes"];
        if (sizeBytes && ![sizeBytes isKindOfClass:[NSNumber class]]) {
            if (errorOut) *errorOut = @"sizeBytes must be a number.";
            return NO;
        }
        
        NSString* newlineMode = entry[@"newlineMode"];
        if (newlineMode) {
            if (![newlineMode isKindOfClass:[NSString class]]) {
                if (errorOut) *errorOut = @"newlineMode must be a string.";
                return NO;
            }
            if (![newlineMode isEqualToString:@"lf"] && ![newlineMode isEqualToString:@"crlf"]) {
                if (errorOut) *errorOut = [NSString stringWithFormat:@"newlineMode has invalid enum value: %@", newlineMode];
                return NO;
            }
        }
        
        NSNumber* wasMissing = entry[@"wasMissing"];
        if (wasMissing && ![wasMissing isKindOfClass:[NSNumber class]]) {
            if (errorOut) *errorOut = @"wasMissing must be a boolean.";
            return NO;
        }
        
        NSNumber* wasBinary = entry[@"wasBinary"];
        if (wasBinary && ![wasBinary isKindOfClass:[NSNumber class]]) {
            if (errorOut) *errorOut = @"wasBinary must be a boolean.";
            return NO;
        }
    }
    
    return YES;
}

- (BOOL)writeManifest:(NSDictionary*)manifest toPath:(NSString*)path error:(NSString**)errorOut {
    NSString* sErr = nil;
    NSString* jsonStr = MacControlCanonicalJsonString(manifest, &sErr);
    if (!jsonStr) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Canonical serialization failed: %@", sErr];
        return NO;
    }
    
    NSData* data = [jsonStr dataUsingEncoding:NSUTF8StringEncoding];
    if (data.length > 256 * 1024) {
        if (errorOut) *errorOut = @"Manifest exceeds maximum allowed size of 256KB.";
        return NO;
    }
    
    NSString* tmpPath = [path stringByAppendingPathExtension:@"tmp"];
    unlink([tmpPath UTF8String]);
    BOOL ok = [data writeToFile:tmpPath atomically:YES];
    if (!ok) {
        if (errorOut) *errorOut = @"Failed to write manifest temp file.";
        return NO;
    }
    
    int fd = open([tmpPath UTF8String], O_RDONLY);
    if (fd >= 0) {
        fsync(fd);
        close(fd);
    }
    
    if (rename([tmpPath UTF8String], [path UTF8String]) != 0) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Atomically renaming manifest failed: %s", strerror(errno)];
        unlink([tmpPath UTF8String]);
        return NO;
    }
    
    NSString* checksum = SHA256ForData(data);
    NSString* checksumPath = [[path stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"manifest.sha256"];
    NSString* tmpChecksumPath = [checksumPath stringByAppendingPathExtension:@"tmp"];
    
    NSError* cErr = nil;
    unlink([tmpChecksumPath UTF8String]);
    BOOL cOk = [checksum writeToFile:tmpChecksumPath atomically:YES encoding:NSUTF8StringEncoding error:&cErr];
    if (!cOk) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to write sha256 temp file: %@", cErr.localizedDescription];
        return NO;
    }
    
    int cFd = open([tmpChecksumPath UTF8String], O_RDONLY);
    if (cFd >= 0) {
        fsync(cFd);
        close(cFd);
    }
    
    if (rename([tmpChecksumPath UTF8String], [checksumPath UTF8String]) != 0) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Atomically renaming sha256 failed: %s", strerror(errno)];
        unlink([tmpChecksumPath UTF8String]);
        return NO;
    }
    
    NSString* parentDir = [path stringByDeletingLastPathComponent];
    int dirFd = open([parentDir UTF8String], O_RDONLY);
    if (dirFd >= 0) {
        fsync(dirFd);
        close(dirFd);
    }
    
    return YES;
}

- (NSDictionary*)loadManifestFromPath:(NSString*)path error:(NSString**)errorOut {
    if (![[NSFileManager defaultManager] fileExistsAtPath:path]) {
        if (errorOut) *errorOut = @"Manifest file missing.";
        return nil;
    }
    
    NSError* err = nil;
    NSDictionary* attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:path error:&err];
    if (attrs) {
        unsigned long long fileSize = [attrs fileSize];
        if (fileSize > 256 * 1024) {
            if (errorOut) *errorOut = @"Manifest exceeds maximum allowed size of 256KB.";
            return nil;
        }
    }
    
    NSData* data = [NSData dataWithContentsOfFile:path options:0 error:&err];
    if (err || !data) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to read manifest: %@", err.localizedDescription];
        return nil;
    }
    
    NSDictionary* manifest = [NSJSONSerialization JSONObjectWithData:data options:0 error:&err];
    if (err || !manifest) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Malformed JSON in manifest: %@", err.localizedDescription];
        return nil;
    }
    
    NSString* valErr = nil;
    if (![self validateManifestStructure:manifest error:&valErr]) {
        if (errorOut) *errorOut = valErr;
        return nil;
    }
    
    NSString* schemaVersion = manifest[@"schemaVersion"] ?: @"1.6.1";
    if ([schemaVersion isEqualToString:@"1.6.2"]) {
        NSString* checksumPath = [[path stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"manifest.sha256"];
        if (![[NSFileManager defaultManager] fileExistsAtPath:checksumPath]) {
            if (errorOut) *errorOut = @"manifest.sha256 file missing.";
            return nil;
        }
        
        NSError* cErr = nil;
        NSString* expectedChecksum = [[NSString stringWithContentsOfFile:checksumPath encoding:NSUTF8StringEncoding error:&cErr] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (cErr || !expectedChecksum) {
            if (errorOut) *errorOut = @"Failed to read manifest.sha256.";
            return nil;
        }
        
        NSString* computedChecksum = SHA256ForData(data);
        if (![computedChecksum isEqualToString:expectedChecksum]) {
            if (errorOut) *errorOut = @"Manifest checksum verification failed.";
            return nil;
        }
    }
    
    return manifest;
}

- (BOOL)createCheckpointForPaths:(NSArray<NSString*>*)paths
                         comboId:(NSString*)comboId
                            plan:(NSDictionary*)plan
                     manifestOut:(NSDictionary**)manifestOut
                    backupDirOut:(NSString**)backupDirOut
                           error:(NSString**)errorOut {
    NSString* ws = [_windowBridge workspacePath];
    if (ws.length == 0) {
        if (errorOut) *errorOut = @"Workspace path is empty.";
        return NO;
    }
    
    std::error_code ec;
    std::filesystem::path wsPath = std::filesystem::canonical(std::filesystem::path(StdStringFromNSString(ws)), ec);
    if (ec) {
        if (errorOut) *errorOut = @"Workspace path cannot be canonicalized.";
        return NO;
    }
    
    NSString* backupDir = [[NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/backups"] stringByAppendingPathComponent:comboId];
    if (![[NSFileManager defaultManager] createDirectoryAtPath:backupDir withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions: @(0700)} error:nil]) {
        if (errorOut) *errorOut = @"Failed to create backup directory.";
        return NO;
    }
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @(0700)} ofItemAtPath:backupDir error:nil];
    
    NSMutableDictionary* manifest = [NSMutableDictionary dictionary];
    manifest[@"schemaVersion"] = @"1.6.2";
    manifest[@"comboId"] = comboId;
    manifest[@"workspaceRootHash"] = StableHashForString(ws);
    manifest[@"createdAt"] = ISODateString([NSDate date]);
    
    NSMutableArray* chipVersions = [NSMutableArray array];
    for (NSDictionary* step in plan[@"steps"] ?: @[]) {
        NSString* chip = step[@"chip"];
        NSString* version = [NSString stringWithFormat:@"%@@%@", chip, step[@"metadata"][@"version"] ?: @1];
        if (![chipVersions containsObject:version]) {
            [chipVersions addObject:version];
        }
    }
    manifest[@"chipVersions"] = chipVersions;
    
    NSMutableArray* filesArray = [NSMutableArray array];
    
    for (NSString* rawPath in paths) {
        NSString* absPath = AbsolutePathForRPCPath(rawPath, ws);
        
        if (!PathIsInsideWorkspace(absPath, ws)) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Path escapes workspace: %@", rawPath];
            [[NSFileManager defaultManager] removeItemAtPath:backupDir error:nil];
            return NO;
        }
        
        std::filesystem::path p(StdStringFromNSString(absPath));
        std::filesystem::path canonicalPath = std::filesystem::exists(p) ? std::filesystem::canonical(p, ec) : std::filesystem::weakly_canonical(p, ec);
        if (ec) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to canonicalize path: %@", rawPath];
            [[NSFileManager defaultManager] removeItemAtPath:backupDir error:nil];
            return NO;
        }
        
        std::filesystem::path rel = std::filesystem::relative(canonicalPath, wsPath, ec);
        if (ec) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to calculate relative path: %@", rawPath];
            [[NSFileManager defaultManager] removeItemAtPath:backupDir error:nil];
            return NO;
        }
        NSString* relPath = NSStringFromStdString(rel.string());
        
        NSMutableDictionary* fileEntry = [NSMutableDictionary dictionary];
        fileEntry[@"workspaceRelativePath"] = relPath;
        fileEntry[@"canonicalPathHash"] = StableHashForString(NSStringFromStdString(canonicalPath.string()));
        
        BOOL isOpen = NO;
        for (NSString* openPath in [_windowBridge openFilePaths]) {
            if ([openPath isEqualToString:absPath]) {
                isOpen = YES;
                break;
            }
        }
        fileEntry[@"domain"] = isOpen ? @"buffer" : @"disk";
        
        BOOL exists = [[NSFileManager defaultManager] fileExistsAtPath:absPath];
        if (exists) {
            NSString* beforeText = [_windowBridge textForFileAtPath:absPath];
            if (beforeText == nil) {
                fileEntry[@"wasBinary"] = @YES;
                fileEntry[@"wasMissing"] = @NO;
                fileEntry[@"sizeBytes"] = @0;
                fileEntry[@"preimageHash"] = @"";
                fileEntry[@"expectedPostimageHash"] = @"";
                fileEntry[@"backupBlobHash"] = @"";
                fileEntry[@"newlineMode"] = @"lf";
            } else {
                BOOL isBin = IsTextBinary(beforeText);
                fileEntry[@"wasBinary"] = @(isBin);
                fileEntry[@"wasMissing"] = @NO;
                
                NSUInteger bytesCount = [beforeText lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
                fileEntry[@"sizeBytes"] = @(bytesCount);
                
                NSString* pHash = StableHashForString(beforeText);
                fileEntry[@"preimageHash"] = pHash;
                fileEntry[@"expectedPostimageHash"] = pHash;
                fileEntry[@"backupBlobHash"] = pHash;
                
                BOOL isCrlf = [beforeText rangeOfString:@"\r\n"].location != NSNotFound;
                fileEntry[@"newlineMode"] = isCrlf ? @"crlf" : @"lf";
                
                if (!isBin) {
                    NSString* blobPath = [backupDir stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.blob", pHash]];
                    NSError* writeErr = nil;
                    BOOL writeOk = [beforeText writeToFile:blobPath atomically:YES encoding:NSUTF8StringEncoding error:&writeErr];
                    if (!writeOk) {
                        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to write preimage blob: %@", writeErr.localizedDescription];
                        [[NSFileManager defaultManager] removeItemAtPath:backupDir error:nil];
                        return NO;
                    }
                    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @(0600)} ofItemAtPath:blobPath error:nil];
                    
                    int fd = open([blobPath UTF8String], O_RDONLY);
                    if (fd >= 0) {
                        fsync(fd);
                        close(fd);
                    }
                }
            }
        } else {
            fileEntry[@"wasBinary"] = @NO;
            fileEntry[@"wasMissing"] = @YES;
            fileEntry[@"sizeBytes"] = @0;
            fileEntry[@"preimageHash"] = @"";
            fileEntry[@"expectedPostimageHash"] = @"";
            fileEntry[@"backupBlobHash"] = @"";
            fileEntry[@"newlineMode"] = @"lf";
        }
        
        [filesArray addObject:fileEntry];
    }
    
    manifest[@"files"] = filesArray;
    
    NSString* manifestPath = [backupDir stringByAppendingPathComponent:@"manifest.json"];
    NSString* mErr = nil;
    if (![self writeManifest:manifest toPath:manifestPath error:&mErr]) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to write manifest: %@", mErr];
        [[NSFileManager defaultManager] removeItemAtPath:backupDir error:nil];
        return NO;
    }
    
    if (manifestOut) *manifestOut = manifest;
    if (backupDirOut) *backupDirOut = backupDir;
    return YES;
}

- (BOOL)restorePatchFromManifest:(NSDictionary*)manifest
                       backupDir:(NSString*)backupDir
                         confirm:(BOOL)confirm
                    sessionToken:(NSString*)sessionToken
                           error:(NSString**)errorOut
                       errorCode:(NSString**)errorCodeOut {
    NSString* ws = [_windowBridge workspacePath];
    if (ws.length == 0) {
        if (errorCodeOut) *errorCodeOut = @"backup_workspace_mismatch";
        if (errorOut) *errorOut = @"No active workspace.";
        return NO;
    }
    
    NSString* manifestWsHash = manifest[@"workspaceRootHash"];
    if (![manifestWsHash isEqualToString:StableHashForString(ws)]) {
        if (errorCodeOut) *errorCodeOut = @"backup_workspace_mismatch";
        if (errorOut) *errorOut = @"Workspace mismatch: backup was created in a different workspace.";
        return NO;
    }
    
    NSString* manifestSession = manifest[@"sessionId"];
    if (manifestSession && sessionToken && ![manifestSession isEqualToString:sessionToken]) {
        if (!confirm) {
            if (errorCodeOut) *errorCodeOut = @"backup_manifest_invalid";
            if (errorOut) *errorOut = @"Session token mismatch. Re-run with confirm=true to override.";
            return NO;
        }
    }
    
    NSArray* files = manifest[@"files"] ?: @[];
    NSMutableDictionary* fileBlobs = [NSMutableDictionary dictionary];
    
    for (NSDictionary* fileEntry in files) {
        NSString* relPath = fileEntry[@"workspaceRelativePath"];
        NSString* absPath = AbsolutePathForRPCPath(relPath, ws);
        
        if (!PathIsInsideWorkspace(absPath, ws)) {
            if (errorCodeOut) *errorCodeOut = @"rollback_target_escaped";
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Target path escapes workspace: %@", relPath];
            return NO;
        }
        
        BOOL wasMissing = [fileEntry[@"wasMissing"] boolValue];
        BOOL wasBinary = [fileEntry[@"wasBinary"] boolValue];
        NSString* expectedPostHash = fileEntry[@"expectedPostimageHash"];
        NSString* preimageHash = fileEntry[@"preimageHash"];
        NSString* blobHash = fileEntry[@"backupBlobHash"];
        
        BOOL exists = [[NSFileManager defaultManager] fileExistsAtPath:absPath];
        
        if (wasMissing) {
            if (exists) {
                NSString* currentText = [_windowBridge textForFileAtPath:absPath];
                NSString* currentHash = StableHashForString(currentText ?: @"");
                if (![currentHash isEqualToString:expectedPostHash]) {
                    if (errorCodeOut) *errorCodeOut = @"rollback_postimage_mismatch";
                    if (errorOut) *errorOut = [NSString stringWithFormat:@"Postimage hash mismatch for new file %@", relPath];
                    return NO;
                }
            }
        } else {
            if (!exists) {
                if (errorCodeOut) *errorCodeOut = @"rollback_postimage_mismatch";
                if (errorOut) *errorOut = [NSString stringWithFormat:@"File was deleted externally: %@", relPath];
                return NO;
            }
            
            NSString* currentText = [_windowBridge textForFileAtPath:absPath];
            if (currentText == nil) {
                if (errorCodeOut) *errorCodeOut = @"rollback_postimage_mismatch";
                if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to read current file content: %@", relPath];
                return NO;
            }
            
            if (IsTextBinary(currentText)) {
                if (errorCodeOut) *errorCodeOut = @"rollback_postimage_mismatch";
                if (errorOut) *errorOut = [NSString stringWithFormat:@"File became binary: %@", relPath];
                return NO;
            }
            
            NSString* currentHash = StableHashForString(currentText);
            if (![currentHash isEqualToString:expectedPostHash]) {
                if (errorCodeOut) *errorCodeOut = @"rollback_postimage_mismatch";
                if (errorOut) *errorOut = [NSString stringWithFormat:@"Postimage hash mismatch for %@", relPath];
                return NO;
            }
            
            if (!wasBinary) {
                NSString* blobPath = [backupDir stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.blob", blobHash]];
                if (![[NSFileManager defaultManager] fileExistsAtPath:blobPath]) {
                    if (errorCodeOut) *errorCodeOut = @"backup_corrupt";
                    if (errorOut) *errorOut = [NSString stringWithFormat:@"Preimage backup blob missing for %@", relPath];
                    return NO;
                }
                
                NSError* readErr = nil;
                NSString* blobText = [NSString stringWithContentsOfFile:blobPath encoding:NSUTF8StringEncoding error:&readErr];
                if (readErr || !blobText) {
                    if (errorCodeOut) *errorCodeOut = @"backup_corrupt";
                    if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to read preimage blob for %@", relPath];
                    return NO;
                }
                
                NSString* computedBlobHash = StableHashForString(blobText);
                if (![computedBlobHash isEqualToString:preimageHash]) {
                    if (errorCodeOut) *errorCodeOut = @"rollback_preimage_mismatch";
                    if (errorOut) *errorOut = [NSString stringWithFormat:@"Blob preimage hash integrity check failed for %@", relPath];
                    return NO;
                }
                
                fileBlobs[absPath] = blobText;
            }
        }
    }
    
    for (NSDictionary* fileEntry in files) {
        NSString* relPath = fileEntry[@"workspaceRelativePath"];
        NSString* absPath = AbsolutePathForRPCPath(relPath, ws);
        BOOL wasMissing = [fileEntry[@"wasMissing"] boolValue];
        BOOL wasBinary = [fileEntry[@"wasBinary"] boolValue];
        
        if (wasMissing) {
            if ([[NSFileManager defaultManager] fileExistsAtPath:absPath]) {
                NSError* deleteErr = nil;
                [[NSFileManager defaultManager] removeItemAtPath:absPath error:&deleteErr];
                
                NSString* currentText = [_windowBridge textForFileAtPath:absPath];
                if (currentText) {
                    [_windowBridge replaceTextInRange:NSMakeRange(0, currentText.length) withText:@"" forFileAtPath:absPath];
                }
            }
        } else {
            if (!wasBinary) {
                NSString* blobText = fileBlobs[absPath];
                NSString* currentText = [_windowBridge textForFileAtPath:absPath];
                [_windowBridge replaceTextInRange:NSMakeRange(0, currentText.length) withText:blobText forFileAtPath:absPath];
                
                NSError* writeErr = nil;
                [blobText writeToFile:absPath atomically:YES encoding:NSUTF8StringEncoding error:&writeErr];
            }
        }
    }
    
    return YES;
}

- (NSDictionary*)performRecoveryScan:(NSString**)errorOut {
    NSString* backupsDir = [NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/backups"];
    BOOL isDir = NO;
    if (![[NSFileManager defaultManager] fileExistsAtPath:backupsDir isDirectory:&isDir] || !isDir) {
        return @{ @"backups": @[] };
    }
    
    NSError* dirErr = nil;
    NSArray* contents = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:backupsDir error:&dirErr];
    if (dirErr) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to list backups directory: %@", dirErr.localizedDescription];
        return nil;
    }
    
    NSMutableArray* backupsReport = [NSMutableArray array];
    NSString* currentWs = [_windowBridge workspacePath];
    
    for (NSString* comboId in contents) {
        NSString* backupDir = [backupsDir stringByAppendingPathComponent:comboId];
        BOOL isSubDir = NO;
        if (![[NSFileManager defaultManager] fileExistsAtPath:backupDir isDirectory:&isSubDir] || !isSubDir) {
            continue;
        }
        
        NSString* manifestPath = [backupDir stringByAppendingPathComponent:@"manifest.json"];
        NSString* mErr = nil;
        NSDictionary* manifest = [self loadManifestFromPath:manifestPath error:&mErr];
        if (!manifest) {
            [backupsReport addObject:@{
                @"comboId": comboId,
                @"status": @"invalid_manifest",
                @"error": mErr ?: @"manifest.json missing or invalid"
            }];
            continue;
        }
        
        NSString* schemaVersion = manifest[@"schemaVersion"] ?: @"1.6.1";
        if (![schemaVersion isEqualToString:@"1.6.2"]) {
            [backupsReport addObject:@{
                @"comboId": comboId,
                @"status": @"unsupported_schema",
                @"error": [NSString stringWithFormat:@"Unsupported schema version: %@", schemaVersion]
            }];
            continue;
        }
        
        NSString* manifestWsHash = manifest[@"workspaceRootHash"];
        BOOL wsMatches = currentWs.length > 0 && [manifestWsHash isEqualToString:StableHashForString(currentWs)];
        if (!wsMatches) {
            [backupsReport addObject:@{
                @"comboId": comboId,
                @"status": @"workspace_mismatch",
                @"error": @"Workspace root hash mismatch."
            }];
            continue;
        }
        
        NSMutableArray* filesReport = [NSMutableArray array];
        NSString* finalStatus = @"valid";
        
        NSArray* files = manifest[@"files"] ?: @[];
        for (NSDictionary* fileEntry in files) {
            NSString* relPath = fileEntry[@"workspaceRelativePath"];
            NSString* absPath = currentWs.length > 0 ? AbsolutePathForRPCPath(relPath, currentWs) : nil;
            NSString* expectedPostHash = fileEntry[@"expectedPostimageHash"];
            NSString* blobHash = fileEntry[@"backupBlobHash"];
            BOOL wasMissing = [fileEntry[@"wasMissing"] boolValue];
            
            NSMutableDictionary* fileRep = [NSMutableDictionary dictionary];
            fileRep[@"workspaceRelativePath"] = relPath;
            
            if (!wasMissing) {
                NSString* blobPath = [backupDir stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.blob", blobHash]];
                if (![[NSFileManager defaultManager] fileExistsAtPath:blobPath]) {
                    finalStatus = @"blob_missing";
                    break;
                }
            }
            
            if (!absPath || !PathIsInsideWorkspace(absPath, currentWs)) {
                finalStatus = @"workspace_mismatch";
                break;
            }
            
            BOOL exists = [[NSFileManager defaultManager] fileExistsAtPath:absPath];
            if (wasMissing) {
                if (exists) {
                    NSString* currentText = [_windowBridge textForFileAtPath:absPath];
                    NSString* currentHash = StableHashForString(currentText ?: @"");
                    if (![currentHash isEqualToString:expectedPostHash]) {
                        finalStatus = @"postimage_mismatch";
                    }
                }
            } else {
                if (!exists) {
                    finalStatus = @"postimage_mismatch";
                } else {
                    NSString* currentText = [_windowBridge textForFileAtPath:absPath];
                    if (currentText == nil || IsTextBinary(currentText)) {
                        finalStatus = @"postimage_mismatch";
                    } else {
                        NSString* currentHash = StableHashForString(currentText);
                        if (![currentHash isEqualToString:expectedPostHash]) {
                            finalStatus = @"postimage_mismatch";
                        }
                    }
                }
            }
            
            fileRep[@"status"] = [finalStatus isEqualToString:@"postimage_mismatch"] ? @"mismatch" : @"match";
            [filesReport addObject:fileRep];
        }
        
        if ([finalStatus isEqualToString:@"valid"]) {
            BOOL allMatched = YES;
            for (NSDictionary* r in filesReport) {
                if ([r[@"status"] isEqualToString:@"mismatch"]) {
                    allMatched = NO;
                    break;
                }
            }
            finalStatus = allMatched ? @"postimage_match" : @"postimage_mismatch";
        }
        
        [backupsReport addObject:@{
            @"comboId": comboId,
            @"createdAt": manifest[@"createdAt"] ?: @"",
            @"status": finalStatus,
            @"files": filesReport
        }];
    }
    
    return @{ @"backups": backupsReport };
}

- (NSArray<NSDictionary*>*)listBackupsQuickWithActiveCombos:(NSDictionary<NSString*, NSDictionary*>*)activeCombos error:(NSString**)errorOut {
    NSString* backupsDir = [NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/backups"];
    BOOL isDir = NO;
    if (![[NSFileManager defaultManager] fileExistsAtPath:backupsDir isDirectory:&isDir] || !isDir) {
        return @[];
    }
    
    NSError* dirErr = nil;
    NSArray* contents = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:backupsDir error:&dirErr];
    if (dirErr) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to list backups directory: %@", dirErr.localizedDescription];
        return nil;
    }
    
    NSMutableArray* list = [NSMutableArray array];
    
    for (NSString* comboId in contents) {
        NSString* backupDir = [backupsDir stringByAppendingPathComponent:comboId];
        BOOL isSubDir = NO;
        if (![[NSFileManager defaultManager] fileExistsAtPath:backupDir isDirectory:&isSubDir] || !isSubDir) {
            continue;
        }
        
        NSString* status = @"valid";
        NSString* createdAt = @"";
        NSString* schemaVersion = @"";
        
        if (activeCombos[comboId]) {
            status = @"active";
            NSDictionary* cInfo = activeCombos[comboId];
            if (cInfo && cInfo[@"createdAt"]) {
                createdAt = cInfo[@"createdAt"];
            }
            if (cInfo && cInfo[@"schemaVersion"]) {
                schemaVersion = cInfo[@"schemaVersion"];
            }
        }
        
        NSString* manifestPath = [backupDir stringByAppendingPathComponent:@"manifest.json"];
        if (![[NSFileManager defaultManager] fileExistsAtPath:manifestPath]) {
            if (![status isEqualToString:@"active"]) {
                status = @"corrupt";
            }
        } else {
            NSData* mData = [NSData dataWithContentsOfFile:manifestPath];
            if (mData) {
                NSDictionary* rawManifest = [NSJSONSerialization JSONObjectWithData:mData options:0 error:nil];
                if ([rawManifest isKindOfClass:[NSDictionary class]]) {
                    if (createdAt.length == 0) {
                        createdAt = rawManifest[@"createdAt"] ?: @"";
                    }
                    schemaVersion = rawManifest[@"schemaVersion"] ?: @"1.6.1";
                }
            }
            
            NSString* mErr = nil;
            NSDictionary* manifest = [self loadManifestFromPath:manifestPath error:&mErr];
            if (!manifest) {
                if (![status isEqualToString:@"active"]) {
                    status = @"corrupt";
                }
            } else {
                if (![status isEqualToString:@"active"]) {
                    if (![schemaVersion isEqualToString:@"1.6.2"]) {
                        status = @"legacy";
                    }
                }
            }
        }
        
        [list addObject:@{
            @"comboId": comboId,
            @"createdAt": createdAt,
            @"schemaVersion": schemaVersion,
            @"status": status
        }];
    }
    
    return list;
}

- (BOOL)deleteBackupWithId:(NSString*)comboId confirm:(BOOL)confirm activeCombos:(NSDictionary<NSString*, NSDictionary*>*)activeCombos error:(NSString**)errorOut errorCode:(NSString**)errorCodeOut {
    NSString* backupsDir = [NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/backups"];
    NSString* backupDir = [backupsDir stringByAppendingPathComponent:comboId];
    
    BOOL isDir = NO;
    if (![[NSFileManager defaultManager] fileExistsAtPath:backupDir isDirectory:&isDir] || !isDir) {
        if (errorCodeOut) *errorCodeOut = @"backup_not_found";
        if (errorOut) *errorOut = @"Backup not found.";
        return NO;
    }
    
    NSString* status = @"valid";
    if (activeCombos[comboId]) {
        status = @"active";
    } else {
        NSString* manifestPath = [backupDir stringByAppendingPathComponent:@"manifest.json"];
        if (![[NSFileManager defaultManager] fileExistsAtPath:manifestPath]) {
            status = @"corrupt";
        } else {
            NSString* mErr = nil;
            NSDictionary* manifest = [self loadManifestFromPath:manifestPath error:&mErr];
            if (!manifest) {
                status = @"corrupt";
            } else {
                NSString* schemaVersion = manifest[@"schemaVersion"] ?: @"1.6.1";
                if (![schemaVersion isEqualToString:@"1.6.2"]) {
                    status = @"legacy";
                }
            }
        }
    }
    
    if ([status isEqualToString:@"active"]) {
        if (errorCodeOut) *errorCodeOut = @"invalid_state";
        if (errorOut) *errorOut = @"Cannot delete active backup.";
        return NO;
    }
    
    if ([status isEqualToString:@"corrupt"]) {
        if (!confirm) {
            if (errorCodeOut) *errorCodeOut = @"confirmation_required";
            if (errorOut) *errorOut = @"Explicit confirmation required to delete corrupt/invalid backup.";
            return NO;
        }
    }
    
    NSError* deleteErr = nil;
    if (![[NSFileManager defaultManager] removeItemAtPath:backupDir error:&deleteErr]) {
        if (errorCodeOut) *errorCodeOut = @"delete_failed";
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to delete backup: %@", deleteErr.localizedDescription];
        return NO;
    }
    
    return YES;
}

- (NSDictionary*)pruneBackupsWithKeepLastN:(NSNumber*)keepLastN olderThanDays:(NSNumber*)olderThanDays dryRun:(BOOL)dryRun confirmInvalid:(BOOL)confirmInvalid activeCombos:(NSDictionary<NSString*, NSDictionary*>*)activeCombos error:(NSString**)errorOut {
    NSArray* list = [self listBackupsQuickWithActiveCombos:activeCombos error:errorOut];
    if (!list) return nil;
    
    NSDateFormatter* parser = [[NSDateFormatter alloc] init];
    parser.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    parser.timeZone = [NSTimeZone timeZoneForSecondsFromGMT:0];
    parser.dateFormat = @"yyyy-MM-dd'T'HH:mm:ss'Z'";
    
    NSArray* sortedList = [list sortedArrayUsingComparator:^NSComparisonResult(NSDictionary* obj1, NSDictionary* obj2) {
        NSString* d1Str = obj1[@"createdAt"];
        NSString* d2Str = obj2[@"createdAt"];
        NSDate* date1 = d1Str.length > 0 ? [parser dateFromString:d1Str] : nil;
        NSDate* date2 = d2Str.length > 0 ? [parser dateFromString:d2Str] : nil;
        if (!date1 && !date2) return NSOrderedSame;
        if (!date1) return NSOrderedDescending;
        if (!date2) return NSOrderedAscending;
        return [date2 compare:date1];
    }];
    
    NSMutableArray* toPrune = [NSMutableArray array];
    NSMutableArray* skipped = [NSMutableArray array];
    
    NSDate* now = [NSDate date];
    
    for (NSUInteger i = 0; i < sortedList.count; i++) {
        NSDictionary* item = sortedList[i];
        NSString* comboId = item[@"comboId"];
        NSString* status = item[@"status"];
        NSString* createdAt = item[@"createdAt"];
        
        BOOL shouldPrune = NO;
        
        if (keepLastN && i >= [keepLastN unsignedIntegerValue]) {
            shouldPrune = YES;
        }
        
        if (olderThanDays && !shouldPrune) {
            NSDate* createdDate = createdAt.length > 0 ? [parser dateFromString:createdAt] : nil;
            if (createdDate) {
                NSTimeInterval ageSeconds = [now timeIntervalSinceDate:createdDate];
                double ageDays = ageSeconds / (24.0 * 3600.0);
                if (ageDays > [olderThanDays doubleValue]) {
                    shouldPrune = YES;
                }
            }
        }
        
        if (shouldPrune) {
            if ([status isEqualToString:@"active"]) {
                [skipped addObject:@{
                    @"comboId": comboId,
                    @"reason": @"Cannot prune active backup."
                }];
            } else if ([status isEqualToString:@"corrupt"]) {
                if (confirmInvalid) {
                    [toPrune addObject:item];
                } else {
                    [skipped addObject:@{
                        @"comboId": comboId,
                        @"reason": @"Explicit confirmation required to delete corrupt/invalid backup."
                    }];
                }
            } else {
                [toPrune addObject:item];
            }
        }
    }
    
    NSMutableArray* prunedIds = [NSMutableArray array];
    if (!dryRun) {
        for (NSDictionary* item in toPrune) {
            NSString* comboId = item[@"comboId"];
            NSString* err = nil;
            NSString* errCode = nil;
            if ([self deleteBackupWithId:comboId confirm:YES activeCombos:activeCombos error:&err errorCode:&errCode]) {
                [prunedIds addObject:comboId];
            } else {
                [skipped addObject:@{
                    @"comboId": comboId,
                    @"reason": err ?: @"Delete failed."
                }];
            }
        }
    } else {
        for (NSDictionary* item in toPrune) {
            [prunedIds addObject:item[@"comboId"]];
        }
    }
    
    return @{
        @"dryRun": @(dryRun),
        @"pruned": prunedIds,
        @"skipped": skipped
    };
}

@end
