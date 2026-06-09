#pragma once

#import <Cocoa/Cocoa.h>

@interface DietCodeSymbolIndexService : NSObject

// Extract symbols from file content on-demand
+ (NSArray<NSDictionary*>*)symbolsForFileContent:(NSString*)content extension:(NSString*)ext;

// Scan workspace on-demand for references to a symbol, with boosting
+ (NSArray<NSDictionary*>*)referencesForSymbol:(NSString*)symbol
                                   inWorkspace:(NSString*)ws
                                     openFiles:(NSArray<NSString*>*)openFiles
                              diagnosticsFiles:(NSArray<NSString*>*)diagFiles;

@end
