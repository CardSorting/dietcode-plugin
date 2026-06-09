#pragma once

#import <Cocoa/Cocoa.h>

NSArray<NSDictionary*>* MacControlRPCMethodDescriptions(void);
NSDictionary* MacControlDescriptionForRPCMethod(NSString* method);
NSArray<NSDictionary*>* MacControlChipRegistry(void);
NSDictionary* MacControlMetadataForChip(NSString* chip);
NSDictionary* MacControlPrimitiveForChip(NSString* chip, NSDictionary* params);
