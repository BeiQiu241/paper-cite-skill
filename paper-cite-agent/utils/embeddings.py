"""句向量相似度计算，用于文献相关性评分。"""

from typing import List, Optional
import math
import re


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingModel:
    """句向量模型封装，优先使用 sentence-transformers，失败则回退到关键词匹配。"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = None
        self._model_name = model_name
        self._available = False
        self._try_load()

    def _try_load(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._available = True
            print(f"  [Embeddings] 已加载模型: {self._model_name}")
        except ImportError:
            print("  [Embeddings] sentence-transformers 未安装，将使用关键词匹配作为回退")
        except Exception as e:
            print(f"  [Embeddings] 模型加载失败: {e}，将使用关键词匹配")

    def encode(self, text: str) -> List[float]:
        """将文本编码为向量。"""
        if self._available and self._model is not None:
            vec = self._model.encode(text)
            return vec.tolist()
        return self._keyword_vector(text)

    def similarity(self, text_a: str, text_b: str) -> float:
        """计算两段文本的语义相似度。"""
        if self._available and self._model is not None:
            vec_a = self.encode(text_a)
            vec_b = self.encode(text_b)
            return cosine_similarity(vec_a, vec_b)
        return self._keyword_similarity(text_a, text_b)

    def _keyword_vector(self, text: str) -> List[float]:
        """基于词频的简单向量（回退方案）。"""
        words = set(text.lower().split())
        return [1.0 if w in words else 0.0 for w in sorted(words)]

    def _keyword_similarity(self, text_a: str, text_b: str) -> float:
        """基于 Jaccard 相似度的关键词匹配，兼容中英文（回退方案）。"""
        def tokenize(text: str) -> set:
            tokens = set()
            # 英文词（长度>2）
            for w in re.findall(r'[a-zA-Z]{3,}', text.lower()):
                tokens.add(w)
            # 中文双字词（bigram）
            zh_chars = re.findall(r'[\u4e00-\u9fff]', text)
            for i in range(len(zh_chars) - 1):
                tokens.add(zh_chars[i] + zh_chars[i + 1])
            return tokens

        words_a = tokenize(text_a)
        words_b = tokenize(text_b)
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)
