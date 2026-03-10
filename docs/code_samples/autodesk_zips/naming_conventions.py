#!/bin/env python

# define Batch Default Iteration Naming
def batchDefaultIterationName( project ):
	pattern = project + "_<batch name>_<date>_<time>_<iteration##>_FPLC"
	return pattern

# define Batch Default Render Node Naming
def batchDefaultRenderNodeName( project ):
	pattern = "<batch name>_<date>_<time>_" + project
	return pattern
