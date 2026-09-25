import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "@/components/chat/chat.css";

interface MarkdownMessageProps {
  text: string;
}

const MarkdownMessage = ({ text }: MarkdownMessageProps) => (
  <div className="agent-markdown">
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
  </div>
);

export default MarkdownMessage;
