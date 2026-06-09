#pragma once

#import <Cocoa/Cocoa.h>

@interface DietCodeWorkspaceAnalysisService : NSObject

// Build situational summary of the workspace
+ (NSDictionary*)summaryOfWorkspace:(NSString*)ws
                          openFiles:(NSArray<NSString*>*)openFiles
                      modifiedFiles:(NSArray<NSString*>*)modifiedFiles
                        diagnostics:(NSDictionary*)diags
                          gitBranch:(NSString*)branch;

// Find imports and TODOs in a file
+ (NSDictionary*)fileSummaryForPath:(NSString*)path symbolsCount:(NSInteger)symCount;

// Find related files based on includes and imports
+ (NSArray<NSString*>*)relatedFilesForPath:(NSString*)path workspace:(NSString*)ws;

// Upgrade grep search with scores, ranking, and context lines
+ (NSArray<NSDictionary*>*)searchRankedForQuery:(NSString*)query
                                      workspace:(NSString*)ws
                                      openFiles:(NSArray<NSString*>*)openFiles
                                    recentFiles:(NSArray<NSString*>*)recentFiles
                                        include:(NSArray<NSString*>*)includes
                                        exclude:(NSArray<NSString*>*)excludes
                                  caseSensitive:(BOOL)caseSensitive;

@end
