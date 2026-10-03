"""End-to-end RAG pipeline: query → (rewrite) → retrieve → generate → validate.

Stateless coordinator. The retriever and generator are injected so the
API layer can build them once at startup (their underlying providers
hold HTTP/qdrant clients that should be reused).

Optional ``query_rewriter`` was added in Sprint 4 after the baseline showed
Chinese questions retrieved unrelated docs from the English corpus. When
present, the rewritten query goes to the retriever (better corpus match)
while the original query goes to the generator (so the answer comes back
in the user's language). When absent, behavior is identical to Sprint 0.
"""

from pydantic import BaseModel

from neblab_rag.rag.answer_validator import AnswerValidation, validate_answer_content
from neblab_rag.rag.multi_hop import MultiHopResult, detect_and_retrieve
from neblab_rag.rag.citation import CitationValidation, validate_citations
from neblab_rag.rag.generator import AnswerGenerator, GeneratedAnswer
from neblab_rag.rag.query_rewriter import QueryRewriter, RewrittenQuery
from neblab_rag.rag.retriever import RetrievedChunk, Retriever


class RAGResult(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    answer: GeneratedAnswer
    citation_validation: CitationValidation
    # Semantic fidelity check (LLM-powered, added in Sprint 5)
    answer_validation: AnswerValidation | None = None
    # Multi-hop retrieval result (Sprint 5)
    multi_hop: MultiHopResult | None = None
    # Optional — only set when QueryRewriter actually changed the query
    rewritten_query: str | None = None


class RAGPipeline:
    def __init__(
        self,
        retriever: Retriever,
        generator: AnswerGenerator,
        *,
        query_rewriter: QueryRewriter | None = None,
    ):
        self._retriever = retriever
        self._generator = generator
        self._rewriter = query_rewriter

    @property
    def retriever(self) -> Retriever:
        return self._retriever

    @property
    def generator(self) -> AnswerGenerator:
        return self._generator

    async def answer(self, *, query: str, top_k: int = 12) -> RAGResult:
        rewritten = await self._maybe_rewrite(query)
        chunks = await self._retriever.retrieve(query=rewritten.rewritten, top_k=top_k)
        answer = await self._generator.generate(query=rewritten.original, chunks=chunks)

        # ── Multi-hop: detect gaps → optional second retrieval ──
        mh_result = None
        if hasattr(self._generator, '_llm'):
            mh_result = await detect_and_retrieve(
                query=rewritten.original,
                first_answer=answer.content,
                first_chunks=chunks,
                retriever=self._retriever,
                llm=self._generator._llm,
                top_k=top_k,
            )
            # If second hop brought new chunks, regenerate with combined chunks
            if mh_result and mh_result.second_chunks:
                answer = await self._generator.generate(
                    query=rewritten.original,
                    chunks=mh_result.final_chunks,
                )

        validation = validate_citations(answer.content, num_chunks=(
            len(mh_result.final_chunks) if mh_result and mh_result.second_chunks
            else len(chunks)
        ))
        # Determine final chunk set (may differ after multi-hop)
        final_chunks = (
            mh_result.final_chunks if mh_result and mh_result.second_chunks
            else chunks
        )
        # Semantic citation fidelity check
        answer_val = None
        if hasattr(self._generator, '_llm'):
            answer_val = await validate_answer_content(
                answer.content, final_chunks, self._generator._llm
            )
        return RAGResult(
            query=query,
            rewritten_query=rewritten.rewritten if rewritten.was_rewritten else None,
            chunks=final_chunks,
            answer=answer,
            citation_validation=validation,
            answer_validation=answer_val,
            multi_hop=mh_result,
        )

    async def _maybe_rewrite(self, query: str) -> RewrittenQuery:
        if self._rewriter is None:
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)
        translated = await self._rewriter.rewrite(query)
        # Expand the retrieved-side query for better recall
        expanded = await self._rewriter.expand(translated.rewritten)
        return RewrittenQuery(
            original=translated.original,
            rewritten=expanded,
            was_rewritten=translated.was_rewritten or (expanded != translated.rewritten),
        )
