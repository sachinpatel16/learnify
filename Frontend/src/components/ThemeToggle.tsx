import React from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface ThemeToggleProps {
  className?: string;
  showLabel?: boolean;
}

const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = '', showLabel = false }) => {
  const { theme, actualTheme, toggleTheme } = useTheme();

  const getIcon = () => {
    if (theme === 'system') {
      return <Monitor className="h-5 w-5" />;
    }
    return actualTheme === 'dark' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />;
  };

  const getLabel = () => {
    switch (theme) {
      case 'light':
        return 'Light';
      case 'dark':
        return 'Dark';
      case 'system':
        return 'System';
      default:
        return 'Theme';
    }
  };

  return (
    <button
      onClick={toggleTheme}
      className={`
        flex items-center space-x-2 px-3 py-2 rounded-lg 
        bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700
        text-gray-700 dark:text-gray-300
        transition-colors duration-200
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900
        ${className}
      `}
      title={`Current theme: ${getLabel()}. Click to cycle through themes.`}
    >
      {getIcon()}
      {showLabel && (
        <span className="text-sm font-medium">
          {getLabel()}
        </span>
      )}
    </button>
  );
};

export default ThemeToggle;
