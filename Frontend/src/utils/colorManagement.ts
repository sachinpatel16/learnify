import React from 'react';

// Color management system for consistent theming
export const colorPalette = {
  // Primary colors
  primary: {
    50: '#eff6ff',
    100: '#dbeafe', 
    200: '#bfdbfe',
    300: '#93c5fd',
    400: '#60a5fa',
    500: '#3b82f6',
    600: '#2563eb',
    700: '#1d4ed8',
    800: '#1e40af',
    900: '#1e3a8a',
    950: '#172554',
  },
  
  // Semantic colors for different features
  semantic: {
    success: {
      light: '#10b981',
      dark: '#059669',
      bg: {
        light: '#ecfdf5',
        dark: '#064e3b',
      },
    },
    warning: {
      light: '#f59e0b',
      dark: '#d97706',
      bg: {
        light: '#fffbeb',
        dark: '#451a03',
      },
    },
    error: {
      light: '#ef4444',
      dark: '#dc2626',
      bg: {
        light: '#fef2f2',
        dark: '#450a0a',
      },
    },
    info: {
      light: '#3b82f6',
      dark: '#2563eb',
      bg: {
        light: '#eff6ff',
        dark: '#1e3a8a',
      },
    },
  },
  
  // Feature-specific colors
  features: {
    documents: {
      light: '#3b82f6',
      dark: '#60a5fa',
      bg: {
        light: '#eff6ff',
        dark: '#1e3a8a',
      },
    },
    hr: {
      light: '#10b981',
      dark: '#34d399',
      bg: {
        light: '#ecfdf5',
        dark: '#064e3b',
      },
    },
    videos: {
      light: '#8b5cf6',
      dark: '#a78bfa',
      bg: {
        light: '#f3e8ff',
        dark: '#581c87',
      },
    },
    chat: {
      light: '#f59e0b',
      dark: '#fbbf24',
      bg: {
        light: '#fffbeb',
        dark: '#451a03',
      },
    },
    prompts: {
      light: '#6366f1',
      dark: '#818cf8',
      bg: {
        light: '#eef2ff',
        dark: '#312e81',
      },
    },
    subscription: {
      light: '#eab308',
      dark: '#facc15',
      bg: {
        light: '#fefce8',
        dark: '#451a03',
      },
    },
  },
  
  // Neutral colors
  neutral: {
    50: '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827',
    950: '#030712',
  },
};

// Utility function to get color classes for components
export const getColorClasses = (feature: keyof typeof colorPalette.features, variant: 'light' | 'dark' = 'light') => {
  const colors = colorPalette.features[feature];
  
  return {
    text: variant === 'light' ? `text-${colors.light.replace('#', '')}` : `text-${colors.dark.replace('#', '')}`,
    bg: variant === 'light' ? `bg-${colors.bg.light.replace('#', '')}` : `bg-${colors.bg.dark.replace('#', '')}`,
    border: variant === 'light' ? `border-${colors.light.replace('#', '')}` : `border-${colors.dark.replace('#', '')}`,
  };
};

// Dark mode aware color classes
export const getThemeAwareClasses = (feature: keyof typeof colorPalette.features) => {
  const colors = colorPalette.features[feature];
  
  return {
    text: `text-${colors.light.replace('#', '')} dark:text-${colors.dark.replace('#', '')}`,
    bg: `bg-${colors.bg.light.replace('#', '')} dark:bg-${colors.bg.dark.replace('#', '')}`,
    border: `border-${colors.light.replace('#', '')} dark:border-${colors.dark.replace('#', '')}`,
    icon: `text-${colors.light.replace('#', '')} dark:text-${colors.dark.replace('#', '')}`,
  };
};

// Component-specific color schemes
export const componentColors = {
  card: {
    background: 'bg-white/80 dark:bg-gray-800/80',
    border: 'border-white/20 dark:border-gray-700/20',
    text: {
      primary: 'text-gray-900 dark:text-white',
      secondary: 'text-gray-600 dark:text-gray-300',
      muted: 'text-gray-500 dark:text-gray-400',
    },
  },
  
  button: {
    primary: 'bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white',
    secondary: 'bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100',
    success: 'bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 text-white',
    warning: 'bg-yellow-600 hover:bg-yellow-700 dark:bg-yellow-500 dark:hover:bg-yellow-600 text-white',
    error: 'bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 text-white',
  },
  
  input: {
    background: 'bg-white dark:bg-gray-700',
    border: 'border-gray-300 dark:border-gray-600',
    text: 'text-gray-900 dark:text-gray-100',
    placeholder: 'placeholder-gray-500 dark:placeholder-gray-400',
    focus: 'focus:ring-blue-500 focus:border-transparent',
  },
  
  alert: {
    success: {
      background: 'bg-green-50 dark:bg-green-900/20',
      border: 'border-green-200 dark:border-green-800',
      text: 'text-green-700 dark:text-green-300',
      icon: 'text-green-500 dark:text-green-400',
    },
    warning: {
      background: 'bg-yellow-50 dark:bg-yellow-900/20',
      border: 'border-yellow-200 dark:border-yellow-800',
      text: 'text-yellow-700 dark:text-yellow-300',
      icon: 'text-yellow-500 dark:text-yellow-400',
    },
    error: {
      background: 'bg-red-50 dark:bg-red-900/20',
      border: 'border-red-200 dark:border-red-800',
      text: 'text-red-700 dark:text-red-300',
      icon: 'text-red-500 dark:text-red-400',
    },
    info: {
      background: 'bg-blue-50 dark:bg-blue-900/20',
      border: 'border-blue-200 dark:border-blue-800',
      text: 'text-blue-700 dark:text-blue-300',
      icon: 'text-blue-500 dark:text-blue-400',
    },
  },
};

// Usage examples and best practices
export const colorUsageExamples = {
  // Card component
  card: `${componentColors.card.background} ${componentColors.card.border} backdrop-blur-lg rounded-2xl shadow-lg p-6`,
  
  // Button component
  primaryButton: `px-4 py-2 rounded-lg font-medium transition-colors duration-200 ${componentColors.button.primary}`,
  
  // Input component
  inputField: `w-full px-3 py-2 rounded-lg transition-colors duration-200 ${componentColors.input.background} ${componentColors.input.border} ${componentColors.input.text} ${componentColors.input.placeholder} ${componentColors.input.focus}`,
  
  // Alert component
  successAlert: `rounded-lg p-4 ${componentColors.alert.success.background} ${componentColors.alert.success.border}`,
  
  // Feature-specific styling
  documentsCard: `${componentColors.card.background} ${componentColors.card.border} backdrop-blur-lg rounded-2xl shadow-lg p-6 hover:shadow-xl transition-shadow`,
  documentsIcon: `p-3 rounded-full ${getThemeAwareClasses('documents').bg}`,
  documentsText: `${getThemeAwareClasses('documents').text}`,
};

export default {
  colorPalette,
  getColorClasses,
  getThemeAwareClasses,
  componentColors,
  colorUsageExamples,
};
