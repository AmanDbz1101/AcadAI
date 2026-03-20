import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from "react";

const paperContent = {
  abstract: {
    title: "Abstract",
    content: `This paper presents a comprehensive analysis of transformer-based architectures and their applications in natural language processing tasks. We investigate the scaling properties of attention mechanisms and propose a novel approach to reduce computational complexity while maintaining model performance. Our experiments demonstrate significant improvements in both training efficiency and inference speed across multiple benchmark datasets. The results suggest that careful architectural modifications can yield substantial practical benefits without sacrificing the representational power that has made transformers the dominant paradigm in modern machine learning.`,
  },
  introduction: {
    title: "Introduction",
    content: `The advent of transformer architectures has fundamentally reshaped the landscape of machine learning research and applications. Since the publication of "Attention Is All You Need" by Vaswani et al. (2017), these models have achieved state-of-the-art performance across a remarkable breadth of tasks spanning natural language processing, computer vision, and multimodal understanding.

However, the computational demands of standard transformer models grow quadratically with sequence length, presenting significant challenges for deployment in resource-constrained environments and for processing long-form documents. This limitation has motivated extensive research into efficient attention mechanisms, sparse transformers, and alternative architectural paradigms.

In this work, we address the fundamental tension between model expressiveness and computational efficiency. We propose a hierarchical attention scheme that decomposes the standard self-attention operation into a series of local and global attention steps, achieving near-linear complexity while preserving the model's ability to capture long-range dependencies.

Our contributions are threefold: (1) we introduce a theoretically grounded framework for analyzing attention complexity, (2) we present a practical implementation that achieves competitive performance with significantly reduced computational overhead, and (3) we provide extensive empirical evaluation across standard benchmarks and novel long-document tasks.`,
  },
  methodology: {
    title: "Methodology",
    content: `Our approach builds upon the standard multi-head self-attention mechanism, which we decompose into two complementary operations: local windowed attention and global summary attention.

Local Windowed Attention. For a given input sequence of length n, we partition the sequence into non-overlapping windows of size w. Within each window, we compute standard self-attention, resulting in O(n · w) complexity rather than O(n²). This captures fine-grained local interactions efficiently.

Global Summary Attention. To preserve the model's ability to reason over long distances, we introduce a set of k learnable summary tokens that attend to the entire sequence. These summary tokens are then broadcast back to all positions, allowing information to flow across window boundaries. The complexity of this step is O(n · k), where k << n.

The combined operation achieves O(n · (w + k)) complexity, which is effectively linear in sequence length for fixed w and k. We integrate this mechanism into a standard transformer encoder-decoder architecture, replacing the self-attention layers while preserving all other components including feedforward networks, layer normalization, and residual connections.

Training Procedure. We employ a two-phase training strategy. In the first phase, we train the model with standard attention on shorter sequences to establish strong representations. In the second phase, we fine-tune with our proposed mechanism on longer sequences, leveraging the pretrained weights as initialization.

Implementation Details. All models are implemented in PyTorch and trained on clusters of 8 NVIDIA A100 GPUs. We use the AdamW optimizer with a cosine learning rate schedule, peak learning rate of 3e-4, and weight decay of 0.01. Batch sizes are adjusted to maximize GPU utilization for each sequence length configuration.`,
  },
  "main-concepts": {
    title: "Main Concepts",
    content: `The theoretical foundation of our work rests on several key concepts from linear algebra and information theory that we briefly review here.

Attention as Kernel Smoothing. The self-attention operation can be interpreted as a form of kernel smoothing, where the softmax function defines a kernel over input positions. This perspective reveals that the quadratic complexity arises from the need to evaluate all pairwise kernel values, and suggests that approximation techniques from the kernel methods literature may be applicable.

Low-Rank Structure of Attention Matrices. Empirical analysis reveals that attention matrices in trained transformers exhibit significant low-rank structure. The effective rank of attention matrices typically decreases with depth, suggesting that deeper layers perform increasingly coarse-grained information aggregation. This observation motivates our use of summary tokens as a low-rank bottleneck.

Information Bottleneck Principle. Our global summary tokens can be understood through the lens of the information bottleneck principle. They compress the full sequence representation into a compact summary that preserves task-relevant information while discarding noise. The number of summary tokens k controls the capacity of this bottleneck.

Locality Bias in Natural Language. Linguistic analysis suggests that the majority of syntactic and semantic dependencies in natural language are local, spanning only a few tokens or sentences. Our windowed attention mechanism exploits this structural property, allocating the majority of computational resources to local interactions where they are most needed.`,
  },
  results: {
    title: "Results",
    content: `We evaluate our approach on four standard benchmarks and two novel long-document tasks. All results are averaged over three random seeds, and we report mean performance with standard deviations.

Standard Benchmarks. On GLUE and SuperGLUE, our model achieves performance within 0.3% of the full-attention baseline while using 47% fewer FLOPs during inference. On the WMT English-German translation task, we observe a BLEU score of 29.8 compared to 30.1 for the baseline, a statistically insignificant difference (p > 0.05).

Long-Document Tasks. The advantages of our approach become more pronounced on longer sequences. On the Long Range Arena benchmark, we achieve a 12% relative improvement in accuracy compared to standard transformers, which struggle with sequences exceeding 4,096 tokens. On our novel BookQA dataset, consisting of questions about full-length novels, we observe a 23% improvement in F1 score.

Computational Efficiency. Training time is reduced by 35% for standard-length tasks and by up to 60% for long-document tasks. Memory consumption scales linearly rather than quadratically, enabling processing of sequences up to 32,768 tokens on a single GPU—an 8× improvement over the standard transformer.

Ablation Studies. Removing the global summary tokens results in a 4.2% drop in performance on tasks requiring long-range reasoning, confirming their importance. Varying the window size w reveals a smooth trade-off between local modeling capacity and computational cost, with w = 256 providing the best balance across our evaluation suite.`,
  },
  discussion: {
    title: "Discussion",
    content: `Our results demonstrate that the tension between computational efficiency and model expressiveness in transformers can be substantially resolved through careful architectural design. The key insight is that natural language exhibits a hierarchical structure that can be exploited: most interactions are local, but a small number of global connections are critical for understanding.

The success of our approach has implications beyond the specific architectural choices we propose. It suggests that the field's reliance on dense attention may represent a form of computational waste—allocating equal resources to all position pairs regardless of their actual relevance. Future work might explore adaptive mechanisms that dynamically allocate attention budget based on input complexity.

We note several limitations of our current approach. First, the optimal values of w and k may be task-dependent, requiring careful hyperparameter tuning. Second, our two-phase training procedure adds complexity to the training pipeline. Third, while our method significantly reduces the computational gap, it does not entirely close it—there may exist even more efficient architectures waiting to be discovered.

The broader impact of efficient attention mechanisms extends to questions of accessibility and environmental sustainability. By reducing the computational requirements of state-of-the-art models, we lower the barrier to entry for researchers and institutions with limited resources, and reduce the carbon footprint associated with training and deploying large language models.`,
  },
  conclusion: {
    title: "Conclusion",
    content: `We have presented a hierarchical attention mechanism that achieves near-linear complexity while maintaining competitive performance with standard transformers. Our approach combines local windowed attention with global summary tokens, exploiting the hierarchical structure of natural language to allocate computational resources efficiently.

Extensive experiments across six benchmarks demonstrate that our method reduces computational cost by 35-60% with minimal impact on model quality. On long-document tasks, our approach not only improves efficiency but also achieves superior performance, suggesting that the inductive biases introduced by our architecture are well-aligned with the structure of real-world language data.

We believe this work represents a step toward making powerful language models more accessible and sustainable. The principles underlying our approach—locality, hierarchy, and compression—are not specific to natural language and may find applications in other domains where transformers are increasingly deployed, including computer vision, protein structure prediction, and scientific simulation.

Future work will explore the integration of our mechanism with other efficiency techniques such as knowledge distillation, quantization, and pruning, with the goal of enabling deployment of high-quality language models on edge devices and in low-resource settings.`,
  },
};

export interface PaperViewerHandle {
  scrollToSection: (sectionId: string) => void;
}

interface PaperViewerProps {
  onVisibleSectionChange: (sectionId: string) => void;
  focusedSection: string | null;
}

const PaperViewer = forwardRef<PaperViewerHandle, PaperViewerProps>(
  ({ onVisibleSectionChange, focusedSection }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

    useImperativeHandle(ref, () => ({
      scrollToSection: (sectionId: string) => {
        const el = sectionRefs.current[sectionId];
        if (el && containerRef.current) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      },
    }));

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      const observer = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((e) => e.isIntersecting)
            .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
          if (visible.length > 0) {
            const id = visible[0].target.getAttribute("data-section");
            if (id) onVisibleSectionChange(id);
          }
        },
        { root: container, rootMargin: "-20% 0px -60% 0px", threshold: 0 }
      );

      Object.values(sectionRefs.current).forEach((el) => {
        if (el) observer.observe(el);
      });

      return () => observer.disconnect();
    }, [onVisibleSectionChange]);

    return (
      <div
        ref={containerRef}
        className="flex-1 h-screen overflow-y-auto scrollbar-thin bg-canvas"
      >
        <div className="max-w-[720px] mx-auto px-6 py-12">
          {/* Paper title */}
          <header className="mb-12">
            <h1 className="font-serif text-[28px] leading-[1.3] font-semibold text-foreground mb-4">
              Hierarchical Attention Mechanisms for Efficient Long-Document Processing in Transformer Architectures
            </h1>
            <p className="font-ui text-[13px] text-text-secondary leading-relaxed">
              Chen, W. · Rodriguez, M. · Nakamura, K. · Okonkwo, A.
            </p>
            <p className="font-ui text-[12px] text-text-secondary opacity-60 mt-1">
              Proceedings of the International Conference on Machine Learning, 2025
            </p>
          </header>

          {/* Paper sections */}
          {Object.entries(paperContent).map(([id, section]) => (
            <section
              key={id}
              data-section={id}
              ref={(el) => { sectionRefs.current[id] = el; }}
              className={`mb-10 transition-opacity duration-600 ${
                focusedSection && focusedSection !== id
                  ? "section-faded"
                  : "section-focused"
              }`}
            >
              <h2 className="font-serif text-[20px] font-semibold text-foreground mb-4">
                {section.title}
              </h2>
              {section.content.split("\n\n").map((paragraph, i) => (
                <p
                  key={i}
                  className="font-serif text-[15px] leading-[1.8] text-foreground mb-4 last:mb-0"
                >
                  {paragraph}
                </p>
              ))}
            </section>
          ))}

          <div className="h-32" />
        </div>
      </div>
    );
  }
);

PaperViewer.displayName = "PaperViewer";
export default PaperViewer;
