'use client';

import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  products?: Product[];
  specialist?: string;
}

interface Product {
  ps_number: string;
  name: string;
  price: number;
  brand: string;
  description: string;
  url: string;
  in_stock: boolean;
  rating: number;
  review_count: number;
  installation_difficulty: string;
}

const SUGGESTED_QUERIES = [
  { icon: '🔧', text: 'How can I install part number PS11752778?' },
  { icon: '🔍', text: 'Is part PS11753379 compatible with my WDT780SAEM1?' },
  { icon: '❄️', text: 'The ice maker on my Whirlpool fridge is not working' },
  { icon: '💧', text: 'My dishwasher is not draining properly' },
];

const SPECIALIST_LABELS: Record<string, string> = {
  product: 'Product Expert',
  repair: 'Repair Expert',
  order: 'Order Support',
  router: 'Assistant',
  guardrails: 'Assistant',
};

function ProductCard({ product }: { product: Product }) {
  const icon = product.name.toLowerCase().includes('dishwasher') ? '🍽️' : '🧊';
  const stars = '★'.repeat(Math.round(product.rating)) + '☆'.repeat(5 - Math.round(product.rating));

  return (
    <a href={product.url} target="_blank" rel="noopener noreferrer" className="product-card">
      <div className="product-card-image">{icon}</div>
      <div className="product-card-info">
        <div className="product-card-name">{product.name}</div>
        <div className="product-card-ps">PS# {product.ps_number} · {product.brand}</div>
        <div className="product-card-meta">
          <span className="product-card-price">${product.price.toFixed(2)}</span>
          <span className="product-card-rating">{stars} ({product.review_count})</span>
          <span className={`product-card-stock ${product.in_stock ? 'in-stock' : 'out-of-stock'}`}>
            {product.in_stock ? '● In Stock' : '○ Out of Stock'}
          </span>
        </div>
        <span className="product-card-difficulty">Install: {product.installation_difficulty}</span>
      </div>
    </a>
  );
}

function TypingIndicator({ specialist }: { specialist?: string }) {
  const label = specialist ? SPECIALIST_LABELS[specialist] || specialist : 'Thinking';
  return (
    <div className="typing-indicator">
      <div className="message-avatar" style={{ background: '#2b6b6a', color: 'white' }}>PS</div>
      <div>
        <div className="typing-specialist">{label}</div>
        <div className="typing-bubble">
          <div className="typing-dot" />
          <div className="typing-dot" />
          <div className="typing-dot" />
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [activeSpecialist, setActiveSpecialist] = useState<string | undefined>();
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, streamingContent]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMessage: Message = { role: 'user', content: text.trim() };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput('');
    setIsLoading(true);
    setStreamingContent('');
    setActiveSpecialist(undefined);

    try {
      const response = await fetch('http://localhost:8000/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
        }),
      });

      if (!response.ok) throw new Error('Failed to get response');

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      let products: Product[] = [];
      let specialist = '';

      if (reader) {
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                if (data.token) {
                  fullText += data.token;
                  const displayText = fullText.replace(/<<<PRODUCT_CARDS:[\s\S]*?>>>/, '').trim();
                  setStreamingContent(displayText);
                }

                if (data.specialist) {
                  specialist = data.specialist;
                  setActiveSpecialist(specialist);
                }

                if (data.products && data.products.length > 0) {
                  products = data.products;
                }
              } catch {
                // Ignore parse errors
              }
            }
          }
        }
      }

      const cleanText = fullText.replace(/<<<PRODUCT_CARDS:[\s\S]*?>>>/, '').trim();
      const assistantMessage: Message = {
        role: 'assistant',
        content: cleanText,
        products: products.length > 0 ? products : undefined,
        specialist,
      };
      setMessages(prev => [...prev, assistantMessage]);
      setStreamingContent('');

    } catch {
      // Fall back to sync endpoint
      try {
        const response = await fetch('http://localhost:8000/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: newMessages.map(m => ({ role: m.role, content: m.content })),
          }),
        });

        if (response.ok) {
          const data = await response.json();
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: data.response,
            products: data.products?.length > 0 ? data.products : undefined,
            specialist: data.specialist,
          }]);
        } else {
          throw new Error('Sync fallback failed');
        }
      } catch {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: "I'm having trouble connecting. Please make sure the backend is running on port 8000.",
        }]);
      }
    } finally {
      setIsLoading(false);
      setStreamingContent('');
      setActiveSpecialist(undefined);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const showWelcome = messages.length === 0;

  return (
    <div className="app-container">
      {/* White header - like PartSelect */}
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">PS</div>
          <div>
            <div className="header-title">PartSelect</div>
            <div className="header-subtitle">Here to help since 1999</div>
          </div>
        </div>
        <div className="header-badge">
          <span className="header-badge-dot" />
          AI Powered
        </div>
      </header>

      {/* Teal nav bar */}
      <nav className="nav-bar">
        <div className="nav-bar-item"><span>🔧</span> Parts Search</div>
        <div className="nav-bar-item"><span>📋</span> Troubleshooting</div>
        <div className="nav-bar-item"><span>🔄</span> Compatibility</div>
        <div className="nav-bar-item"><span>📦</span> Order Status</div>
        <div className="nav-bar-item"><span>📖</span> Install Guides</div>
      </nav>

      {/* Benefits bar */}
      <div className="benefits-bar">
        <div className="benefit-item"><span className="benefit-icon">💰</span> Price Match Guarantee</div>
        <div className="benefit-item"><span className="benefit-icon">🚚</span> Fast Shipping</div>
        <div className="benefit-item"><span className="benefit-icon">✓</span> Genuine OEM Parts</div>
        <div className="benefit-item"><span className="benefit-icon">🛡️</span> 1 Year Warranty</div>
      </div>

      <div className="chat-area" ref={chatAreaRef}>
        {showWelcome ? (
          <div className="welcome-container">
            {/* Golden hero section like PartSelect */}
            <div className="welcome-hero">
              <div className="welcome-hero-title">How Can I Help You Today?</div>
              <div className="welcome-hero-subtitle">
                Your AI assistant for refrigerator &amp; dishwasher parts
              </div>
              <div className="welcome-features">
                <div className="welcome-feature">
                  <span className="welcome-feature-check">✔</span> Find the right part for your model
                </div>
                <div className="welcome-feature">
                  <span className="welcome-feature-check">✔</span> Step-by-step repair guidance
                </div>
                <div className="welcome-feature">
                  <span className="welcome-feature-check">✔</span> Compatibility verification
                </div>
              </div>
            </div>

            <div className="suggested-queries">
              {SUGGESTED_QUERIES.map((query, i) => (
                <button key={i} className="suggested-query" onClick={() => sendMessage(query.text)}>
                  <span className="suggested-query-icon">{query.icon}</span>
                  {query.text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((message, i) => (
              <div key={i} className={`message message-${message.role}`}>
                <div className="message-avatar">
                  {message.role === 'assistant' ? 'PS' : '👤'}
                </div>
                <div>
                  {message.specialist && message.role === 'assistant' && (
                    <div className="message-specialist">
                      {SPECIALIST_LABELS[message.specialist] || message.specialist}
                    </div>
                  )}
                  <div className="message-bubble">
                    {message.role === 'assistant' ? (
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    ) : (
                      message.content
                    )}
                  </div>
                  {message.products && message.products.length > 0 && (
                    <div className="product-cards-container">
                      {message.products.map((product, j) => (
                        <ProductCard key={j} product={product} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {streamingContent && (
              <div className="message message-assistant">
                <div className="message-avatar">PS</div>
                <div>
                  {activeSpecialist && (
                    <div className="message-specialist">
                      {SPECIALIST_LABELS[activeSpecialist] || activeSpecialist}
                    </div>
                  )}
                  <div className="message-bubble streaming">
                    <ReactMarkdown>{streamingContent}</ReactMarkdown>
                    <span className="cursor-blink">▊</span>
                  </div>
                </div>
              </div>
            )}

            {isLoading && !streamingContent && <TypingIndicator specialist={activeSpecialist} />}
          </>
        )}
      </div>

      <div className="input-container">
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            className="input-field"
            placeholder="Search model # or part # or describe your problem..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isLoading}
          />
          <button
            className="send-button"
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isLoading}
            aria-label="Send message"
          >
            ➤
          </button>
        </div>
        <div className="input-hint">
          Specializing in refrigerator &amp; dishwasher parts · Powered by AI
        </div>
      </div>
    </div>
  );
}
