# Amazon Bedrock + OpenSearch RAG
- aws s3api create-bucket --bucket rag-devops-project --region us-east-1
## 📌 Overview

This project demonstrates a simple **Retrieval-Augmented Generation (RAG)** architecture using:

* **Amazon Bedrock** – Embeddings and LLM
* **Amazon Titan Embeddings** – Converts text into vectors
* **Amazon OpenSearch** – Stores vectors and performs similarity search
* **RAG** – Retrieves relevant information before generating the answer

The main idea is:

```text
User Question
      ↓
Bedrock Embedding Model
      ↓
Query Vector
      ↓
OpenSearch Vector Search
      ↓
Top K Relevant Chunks
      ↓
Bedrock LLM
      ↓
Final Answer
```

---

# 1. What is RAG?

RAG stands for:

> **Retrieval-Augmented Generation**

Instead of asking an LLM to answer a question only from its trained knowledge, we first retrieve relevant information from our own data.

For example:

```text
User:
"What is Amazon S3?"
```

The application searches our knowledge base and retrieves relevant content such as:

```text
Amazon S3 is an object storage service.

S3 provides scalable object storage.

S3 supports multiple storage classes.
```

These retrieved chunks are then provided to the LLM.

The LLM generates the final answer using the retrieved context.

---

# 2. High-Level Architecture

```text
                    ┌─────────────────────┐
                    │       User          │
                    │ "What is Amazon S3?"│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Your Application   │
                    │   Python / API      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Amazon Bedrock    │
                    │ Titan Embeddings    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Query Vector     │
                    │ [0.12,-0.34,0.78...]│
                    │    1024 dimensions  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    OpenSearch       │
                    │  Vector Search      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Top K Similar Chunks│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Prompt + Context  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Amazon Bedrock    │
                    │        LLM          │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Final Answer     │
                    └─────────────────────┘
```

---

# 3. Important Concept: There Are Two Bedrock Operations

A common beginner question is:

> "Why are we calling Bedrock twice?"

Because there are two different jobs.

### Operation 1 — Embedding

Convert text into a vector.

```text
Text
 ↓
Embedding Model
 ↓
Vector
```

### Operation 2 — Generation

Convert context + question into a human-readable answer.

```text
Question + Context
        ↓
       LLM
        ↓
     Answer
```

---

# 4. RAG Has Two Main Phases

## Phase 1 — Data Ingestion

Before users ask questions, we need to prepare our documents.

```text
Documents
    ↓
Load Documents
    ↓
Split into Chunks
    ↓
Generate Embeddings
    ↓
Store Vectors
    ↓
OpenSearch
```

For example:

```text
S3 Documentation
        ↓
Document Loader
        ↓
Text
        ↓
Chunking
        ↓
Chunk 1
Chunk 2
Chunk 3
Chunk 4
        ↓
Titan Embeddings
        ↓
Vector 1
Vector 2
Vector 3
Vector 4
        ↓
OpenSearch
```

---

# 5. Example Documents

Suppose we have the following document:

```text
Amazon S3 is an object storage service.

Amazon S3 provides scalable storage for data.

S3 stores objects inside buckets.

Amazon S3 supports multiple storage classes.
```

We split this document into smaller chunks.

For example:

```text
Chunk 1:
Amazon S3 is an object storage service.

Chunk 2:
Amazon S3 provides scalable storage for data.

Chunk 3:
S3 stores objects inside buckets.

Chunk 4:
Amazon S3 supports multiple storage classes.
```

---

# 6. Generate Embeddings

Each chunk is sent to the embedding model.

```text
Chunk 1
   ↓
Titan Embedding Model
   ↓
Vector 1
```

Similarly:

```text
Chunk 2 → Vector 2
Chunk 3 → Vector 3
Chunk 4 → Vector 4
```

Conceptually:

```text
Chunk 1
   ↓
[0.12, -0.34, 0.78, ...]

Chunk 2
   ↓
[0.42, 0.18, -0.22, ...]

Chunk 3
   ↓
[-0.15, 0.81, 0.34, ...]

Chunk 4
   ↓
[0.52, -0.27, 0.63, ...]
```

These vectors represent the **semantic meaning** of the text.

---

# 7. Store Vectors in OpenSearch

OpenSearch stores both:

1. The original text
2. The vector representation

Conceptually:

```text
OpenSearch

Document 1
--------------------------------
Text:
"Amazon S3 is an object storage service."

Vector:
[0.12, -0.34, 0.78, ...]
--------------------------------

Document 2
--------------------------------
Text:
"S3 provides scalable object storage."

Vector:
[0.42, 0.18, -0.22, ...]
--------------------------------
```

This is important.

OpenSearch does not only store the vector.

We normally keep the original chunk text as well.

Why?

Because after similarity search, we need the **actual text** to send to the LLM.

---

# 8. User Asks a Question

Now the user asks:

```text
What is Amazon S3?
```

The application receives the question.

```text
User
 │
 │ "What is Amazon S3?"
 ▼
Application
```

---

# 9. Convert User Question into a Vector

The question is sent to the same embedding model.

```text
"What is Amazon S3?"
        ↓
Titan Embeddings
        ↓
Query Vector
```

For example:

```text
[0.12, -0.34, 0.78, ...]
```

The actual vector will contain many dimensions.

For the model being used, the vector dimensionality must match the OpenSearch vector field configuration.

---

# 10. Send Query Vector to OpenSearch

Now the application sends the query vector to OpenSearch.

```text
Query Vector
     │
     ▼
OpenSearch
```

OpenSearch compares the query vector against the stored document vectors.

```text
                 Query Vector
                      │
          ┌───────────┼───────────┐
          ↓           ↓           ↓
       Vector 1    Vector 2    Vector 3
          │           │           │
          └───────────┼───────────┘
                      ↓
               Similarity Search
                      ↓
                 Top K Results
```

---

# 11. What Does Similarity Mean?

Suppose OpenSearch calculates similarity scores.

Example:

```text
Query:
"What is Amazon S3?"
```

Search results:

```text
Chunk 7   → 0.92
Chunk 2   → 0.88
Chunk 15  → 0.83
Chunk 4   → 0.61
Chunk 20  → 0.42
```

Higher similarity means the stored vector is closer to the query vector according to the configured similarity/search method.

If we request:

```text
Top K = 3
```

we retrieve:

```text
Chunk 7
Chunk 2
Chunk 15
```

---

# 12. OpenSearch Returns the Actual Text

This is a very important step.

OpenSearch does not simply return:

```text
0.92
0.88
0.83
```

It returns the documents/chunks associated with those search results.

For example:

```text
Chunk 7:
"Amazon S3 is an object storage service..."

Chunk 2:
"S3 provides scalable object storage..."

Chunk 15:
"S3 supports multiple storage classes..."
```

Now we have useful context.

---

# 13. Build the RAG Prompt

The application combines:

```text
User Question
+
Retrieved Chunks
```

For example:

```text
System:
Answer the question using the provided context.

Context:

Amazon S3 is an object storage service.

S3 provides scalable object storage.

S3 supports multiple storage classes.

Question:

What is Amazon S3?
```

This entire prompt is sent to the LLM.

---

# 14. Bedrock LLM Generates the Answer

Now the second Bedrock operation happens.

```text
Context + Question
        ↓
Amazon Bedrock LLM
        ↓
Generated Answer
```

Example answer:

```text
Amazon S3 is an AWS object storage service that
provides scalable storage for data. It stores data
as objects inside buckets and supports multiple
storage classes for different access requirements.
```

---

# 15. Complete End-to-End Flow

The complete process is:

```text
                       INGESTION PHASE
                       ================

Documents
    │
    ▼
Document Loader
    │
    ▼
Text Chunking
    │
    ▼
Document Chunks
    │
    ▼
Amazon Bedrock
Titan Embeddings
    │
    ▼
Vectors
    │
    ▼
OpenSearch
    │
    ├── Chunk Text
    └── Chunk Vector


                       QUERY PHASE
                       ============

User Question
    │
    │ "What is Amazon S3?"
    ▼
Your Application
    │
    ▼
Amazon Bedrock
Titan Embeddings
    │
    ▼
Query Vector
    │
    ▼
OpenSearch
    │
    ▼
Similarity Search
    │
    ▼
Top K Relevant Chunks
    │
    ▼
Context + User Question
    │
    ▼
Amazon Bedrock LLM
    │
    ▼
Final Answer
```

---

# 16. Simple Architecture

```text
                 ┌───────────────┐
                 │   Documents   │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │    Chunking   │
                 └───────┬───────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Amazon Bedrock   │
                │ Titan Embeddings │
                └────────┬─────────┘
                         │
                         ▼
                 ┌───────────────┐
                 │   Vectors     │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │  OpenSearch   │
                 │ Vector Index  │
                 └───────────────┘


User
 │
 │ "What is Amazon S3?"
 ▼
Application
 │
 ▼
Bedrock Embeddings
 │
 ▼
Query Vector
 │
 ▼
OpenSearch
 │
 ▼
Top K Chunks
 │
 ▼
Context + Question
 │
 ▼
Bedrock LLM
 │
 ▼
Answer
```

---

# 17. Why Do We Need Embeddings?

Traditional keyword search looks for matching words.

For example:

```text
Query:
"object storage"
```

Keyword search looks for:

```text
object
storage
```

Vector search understands semantic similarity.

For example:

```text
Query:
"Where can I store files in AWS?"
```

It can retrieve:

```text
"Amazon S3 is an object storage service."
```

Even though the exact words may be different.

This is one of the major advantages of vector search in RAG.

---

# 18. Why Do We Need OpenSearch?

The embedding model creates the vector.

It does **not** normally act as our complete vector database.

OpenSearch provides:

```text
Vector Storage
       +
Vector Search
       +
Metadata
       +
Original Document/Chunk
```

Therefore:

```text
Bedrock Embedding
       ↓
Creates vector

OpenSearch
       ↓
Stores + searches vector
```

---

# 19. Why Do We Need the LLM?

OpenSearch retrieves information.

It does not normally produce the final natural-language answer.

For example, OpenSearch may return:

```text
Chunk 1:
"S3 is an object storage service."

Chunk 2:
"S3 stores objects inside buckets."

Chunk 3:
"S3 supports multiple storage classes."
```

The LLM uses those chunks to create:

```text
Amazon S3 is an AWS object storage service that
stores objects in buckets and provides multiple
storage classes.
```

Therefore:

```text
Embedding Model
      ↓
Find relevant information

OpenSearch
      ↓
Retrieve relevant information

LLM
      ↓
Generate the answer
```

---

# 20. Two Different Bedrock Models/Operations

It is useful to understand that **embedding and generation are different tasks**.

### Embedding

```text
Text
 ↓
Embedding Model
 ↓
Vector
```

Used for:

* Semantic search
* Similarity search
* Retrieval

### Generation

```text
Prompt
 ↓
LLM
 ↓
Text Answer
```

Used for:

* Question answering
* Summarization
* Reasoning
* Text generation

So the RAG application can look like:

```text
                Amazon Bedrock
                ┌──────────────┐
                │              │
                │ Embeddings   │
                │     ↓        │
                │   Vector     │
                │              │
                │     LLM      │
                │     ↓        │
                │   Answer     │
                └──────────────┘
```

---

# 21. Example End-to-End Scenario

Suppose we have an AWS documentation PDF.

```text
aws-s3-documentation.pdf
```

## Step 1 — Load

```text
PDF
 ↓
Document Loader
```

## Step 2 — Split

```text
PDF
 ↓
Chunk 1
Chunk 2
Chunk 3
...
Chunk 100
```

## Step 3 — Embed

```text
Chunk 1 → Embedding → Vector 1
Chunk 2 → Embedding → Vector 2
Chunk 3 → Embedding → Vector 3
...
Chunk 100 → Embedding → Vector 100
```

## Step 4 — Store

```text
OpenSearch

Chunk 1 + Vector 1
Chunk 2 + Vector 2
Chunk 3 + Vector 3
...
Chunk 100 + Vector 100
```

## Step 5 — User Question

```text
"What is Amazon S3?"
```

## Step 6 — Embed Question

```text
Question
   ↓
Titan Embedding
   ↓
Query Vector
```

## Step 7 — Search

```text
Query Vector
     ↓
OpenSearch
     ↓
Similarity Search
     ↓
Top 3 chunks
```

## Step 8 — Build Prompt

```text
Context:
Chunk 7
Chunk 2
Chunk 15

Question:
What is Amazon S3?
```

## Step 9 — Generate

```text
Prompt
 ↓
Bedrock LLM
 ↓
Final Answer
```

---

# 22. The Most Important Mental Model

Remember this simple formula:

```text
RAG = Retrieve + Generate
```

More specifically:

```text
                 RETRIEVE
                    │
Question ──→ Embedding ──→ Vector Search
                              │
                              ▼
                         Relevant Chunks
                              │
                              │
                              ▼
                 GENERATE
                    │
                    ▼
             LLM + Context
                    │
                    ▼
                 Answer
```

---

# 23. What Is Stored in OpenSearch?

A simplified OpenSearch document might look like:

```json
{
  "text": "Amazon S3 is an object storage service.",
  "vector": [0.12, -0.34, 0.78, "..."],
  "source": "s3-documentation.pdf",
  "page": 10
}
```

The exact index mapping depends on your OpenSearch configuration.

The important concept is:

```text
text
 +
vector
 +
metadata
```

---

# 24. What Does Top K Mean?

Suppose we have:

```text
1000 chunks
```

The query is:

```text
"What is Amazon S3?"
```

We don't want to send all 1000 chunks to the LLM.

Instead:

```text
1000 chunks
     ↓
Similarity Search
     ↓
Top K = 3
     ↓
3 relevant chunks
```

For example:

```text
Chunk 7   → 0.92
Chunk 2   → 0.88
Chunk 15  → 0.83
```

Those 3 chunks become the context.

---

# 25. Important Difference: Vector ≠ Text

This is a critical concept for beginners.

A vector might look like:

```text
[0.12, -0.34, 0.78, ...]
```

The LLM should not normally receive only this vector as context.

Instead:

```text
Vector
  ↓
OpenSearch Search
  ↓
Matching Document
  ↓
Original Text Chunk
```

For example:

```text
Vector
 ↓
Similarity Search
 ↓
Chunk:
"Amazon S3 is an object storage service."
```

Then:

```text
Chunk Text
   ↓
LLM
```

---

# 26. Final Flow in One Diagram

```text
                         INGESTION
                         =========

       Document
           │
           ▼
    ┌──────────────┐
    │   Chunking   │
    └──────┬───────┘
           │
           ▼
    ┌─────────────────┐
    │ Bedrock         │
    │ Titan Embedding │
    └──────┬──────────┘
           │
           ▼
        Vector
           │
           ▼
    ┌─────────────────┐
    │   OpenSearch    │
    │                 │
    │ Text + Vector   │
    └─────────────────┘


                          QUERY
                          =====

      User Question
           │
           ▼
    ┌─────────────────┐
    │ Bedrock         │
    │ Titan Embedding │
    └──────┬──────────┘
           │
           ▼
      Query Vector
           │
           ▼
    ┌─────────────────┐
    │   OpenSearch    │
    │                 │
    │ Vector Search   │
    └──────┬──────────┘
           │
           ▼
      Top K Chunks
           │
           ▼
   ┌──────────────────────┐
   │ Question + Context   │
   └──────────┬───────────┘
              │
              ▼
      ┌────────────────┐
      │ Bedrock LLM    │
      └───────┬────────┘
              │
              ▼
        Final Answer
```

---

# 27. Key Takeaways

Remember these points:

### 1. Documents are chunked

```text
Document → Chunks
```

### 2. Chunks become vectors

```text
Chunk → Bedrock Embedding → Vector
```

### 3. Vectors are stored in OpenSearch

```text
Vector + Text + Metadata → OpenSearch
```

### 4. User question also becomes a vector

```text
Question → Bedrock Embedding → Query Vector
```

### 5. OpenSearch performs similarity search

```text
Query Vector
     ↓
Stored Vectors
     ↓
Similarity
     ↓
Top K
```

### 6. Actual text chunks are retrieved

```text
Top K Vectors
     ↓
Original Text Chunks
```

### 7. LLM receives question + retrieved context

```text
Question + Context
        ↓
      Bedrock
        ↓
      Answer
```

---

# 28. One-Line Interview Explanation

If someone asks:

> **"Explain your RAG architecture."**

You can say:

> "During ingestion, I split documents into chunks, generate embeddings using Amazon Bedrock, and store the vectors along with the original chunks in OpenSearch. During a user query, I generate an embedding for the question, perform vector similarity search in OpenSearch to retrieve the top-K relevant chunks, and pass those chunks along with the question to a Bedrock LLM to generate the final grounded response."

---

# 29. Complete Formula

```text
             INGESTION

Document
   ↓
Chunk
   ↓
Embedding
   ↓
Vector
   ↓
OpenSearch


             QUERY

Question
   ↓
Embedding
   ↓
Query Vector
   ↓
OpenSearch
   ↓
Top K Chunks
   ↓
Prompt
   ↓
Bedrock LLM
   ↓
Answer
```

### Final mental model

```text
Embedding Model = "Convert meaning into numbers"

OpenSearch = "Find similar information"

LLM = "Use the information to generate an answer"

RAG = "Find the right information first, then ask the LLM to answer using it."
```
