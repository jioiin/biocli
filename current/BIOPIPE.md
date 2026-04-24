# Project: Mouse Liver Transcriptomics

organism: Mus musculus
genome: mm39
sequencing: paired-end Illumina NovaSeq 6000
adapters: TruSeq

## Cluster
cluster: Stanford Sherlock
partition: normal
max_nodes: 1
max_time: 12:00:00

## Conventions
conventions:
  - All output in ./results/{sample_name}/
  - Use fastp for trimming, not trimmomatic
  - STAR aligner preferred for RNA-seq
  - Always add Read Groups before GATK
  - Minimum base quality: Phred 20
  - Minimum read length after trimming: 50bp
  - Generate MultiQC report at the end of every pipeline
  - Comment every non-obvious flag
