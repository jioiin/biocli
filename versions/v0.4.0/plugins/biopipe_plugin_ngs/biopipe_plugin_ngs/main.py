from biopipe.core.types import Tool, PermissionLevel, ToolResult

class NGSWorkflowGeneratorTool(Tool):
    """Generates standard NGS pipelines."""

    @property
    def name(self) -> str:
        return "ngs_workflow_generator"

    @property
    def description(self) -> str:
        return "Generates standard bash/snakemake pipelines for RNA-seq or WGS."

    def required_permission(self) -> PermissionLevel:
        return PermissionLevel.GENERATE

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "assay": {"type": "string", "enum": ["rna-seq", "wgs", "qc"]},
                "genome": {"type": "string", "description": "e.g., hg38"}
            },
            "required": ["assay"]
        }

    def execute(self, **kwargs) -> ToolResult:
        assay = kwargs.get("assay")
        genome = kwargs.get("genome", "hg38")
        
        output = f"echo 'Running {assay} pipeline on {genome}'\n"
        if assay == "rna-seq":
            output += "fastqc *.fastq.gz\n"
            output += f"star --genomeDir /db/star/{genome} --readFilesIn reads.fq.gz\n"
            
        return ToolResult(output=output)
