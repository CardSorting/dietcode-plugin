#pragma once

#import <Cocoa/Cocoa.h>

@interface DietCodeDiffAnalysisService : NSObject

// Get status, modifications, and preview patches across workspace
+ (NSDictionary*)workspaceDiffInfo:(NSString*)ws;

// Simulate patch application and evaluate risk, affected symbols, and syntax errors
+ (NSDictionary*)previewPatchAtPath:(NSString*)path
                              patch:(NSString*)patch
                        currentText:(NSString*)currentText
                            symbols:(NSArray<NSDictionary*>*)symbols;

@end
