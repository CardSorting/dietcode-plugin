#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;

@interface MacControlRecoveryStore : NSObject

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge;

- (BOOL)createCheckpointForPaths:(NSArray<NSString*>*)paths
                         comboId:(NSString*)comboId
                            plan:(NSDictionary*)plan
                     manifestOut:(NSDictionary**)manifestOut
                    backupDirOut:(NSString**)backupDirOut
                           error:(NSString**)errorOut;

- (BOOL)restorePatchFromManifest:(NSDictionary*)manifest
                       backupDir:(NSString*)backupDir
                         confirm:(BOOL)confirm
                    sessionToken:(NSString*)sessionToken
                           error:(NSString**)errorOut
                       errorCode:(NSString**)errorCodeOut;

- (NSDictionary*)performRecoveryScan:(NSString**)errorOut;

- (NSArray<NSDictionary*>*)listBackupsQuickWithActiveCombos:(NSDictionary<NSString*, NSDictionary*>*)activeCombos 
                                                     error:(NSString**)errorOut;

- (BOOL)deleteBackupWithId:(NSString*)comboId 
                   confirm:(BOOL)confirm 
              activeCombos:(NSDictionary<NSString*, NSDictionary*>*)activeCombos 
                     error:(NSString**)errorOut 
                 errorCode:(NSString**)errorCodeOut;

- (NSDictionary*)pruneBackupsWithKeepLastN:(NSNumber*)keepLastN 
                             olderThanDays:(NSNumber*)olderThanDays 
                                    dryRun:(BOOL)dryRun 
                            confirmInvalid:(BOOL)confirmInvalid 
                              activeCombos:(NSDictionary<NSString*, NSDictionary*>*)activeCombos 
                                     error:(NSString**)errorOut;

- (BOOL)writeManifest:(NSDictionary*)manifest toPath:(NSString*)path error:(NSString**)errorOut;
- (NSDictionary*)loadManifestFromPath:(NSString*)path error:(NSString**)errorOut;
- (BOOL)validateManifestStructure:(NSDictionary*)manifest error:(NSString**)errorOut;

@end
