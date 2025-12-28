#!/bin/bash

INPUT_DIR=inputs
OUTPUT_DIR=outputs
PSEUDO_DIR=PWscf

mkdir -p $OUTPUT_DIR

for infile in $INPUT_DIR/*.in; do
    name=$(basename $infile .in)
    mpirun -np 16 pw.x < $infile > $OUTPUT_DIR/$name.out
done
