import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import Layout from './components/Layout';
import BooksPage from './components/pages/BooksPage';
import ChatbotPage from './components/pages/ChatbotPage';
import DocumentsPage from './components/pages/DocumentsPage';

type AppPage = 'books' | 'documents' | 'chat';

const AppContent: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<AppPage>('books');
  const renderCurrentPage = () => {
    switch (currentPage) {
      case 'books':
        return <BooksPage />;
      case 'chat':
        return <ChatbotPage />;
      case 'documents':
        return <DocumentsPage />;
      default:
        return <BooksPage />;
    }
  };

  return (
    <Layout currentPage={currentPage} onPageChange={setCurrentPage}>
      {renderCurrentPage()}
    </Layout>
  );
};

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}

export default App;