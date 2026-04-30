import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import Layout from './components/Layout';
import BooksPage from './components/pages/BooksPage';
import ExamReaderPage from './components/pages/ExamReaderPage';

type AppPage = 'books' | 'examReader';

const AppContent: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<AppPage>('books');
  const renderCurrentPage = () => {
    switch (currentPage) {
      case 'books':
        return <BooksPage />;
      case 'examReader':
        return <ExamReaderPage />;
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