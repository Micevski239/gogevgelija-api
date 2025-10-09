// Multilingual Tabs JavaScript
(function ($) {
    $(document).ready(function () {
        initMultilingualTabs();

        // Save selected tab to localStorage
        function saveSelectedTab(tabId) {
            localStorage.setItem('selectedLangTab', tabId);
        }

        // Get selected tab from localStorage
        function getSelectedTab() {
            return localStorage.getItem('selectedLangTab') || 'en';
        }

        function initMultilingualTabs() {
            // Find all fieldsets with lang-tab class
            var langFieldsets = $('.lang-tab');

            if (langFieldsets.length === 0) {
                return; // No multilingual fields found
            }

            // Create tabs container
            var tabsContainer = $('<div class="lang-tabs"></div>');
            var tabHeaders = $('<div class="tab-headers"></div>');
            var tabContents = $('<div class="tab-contents"></div>');

            // Languages configuration
            var languages = [
                { code: 'en', name: 'English', class: 'lang-en' },
                { code: 'mk', name: 'Македонски', class: 'lang-mk' }
            ];

            // Group fieldsets by language
            var langGroups = {};
            languages.forEach(function (lang) {
                langGroups[lang.code] = [];
            });

            // Categorize fieldsets
            langFieldsets.each(function () {
                var fieldset = $(this);
                var classes = fieldset.attr('class').split(' ');

                for (var i = 0; i < classes.length; i++) {
                    var className = classes[i];
                    if (className.startsWith('lang-') && className !== 'lang-tab') {
                        var langCode = className.replace('lang-', '');
                        if (langGroups[langCode]) {
                            langGroups[langCode].push(fieldset);
                        }
                    }
                }
            });

            // Create tab headers
            languages.forEach(function (lang) {
                if (langGroups[lang.code].length > 0) {
                    var tabHeader = $('<div class="lang-tab-header ' + lang.class + '" data-lang="' + lang.code + '">' + lang.name + '</div>');
                    tabHeaders.append(tabHeader);
                }
            });

            // Create tab contents
            languages.forEach(function (lang) {
                if (langGroups[lang.code].length > 0) {
                    var tabContent = $('<div class="lang-tab-content" data-lang="' + lang.code + '"></div>');

                    // Move fieldsets to tab content
                    langGroups[lang.code].forEach(function (fieldset) {
                        // Remove the fieldset wrapper but keep the content
                        var content = fieldset.find('.module').length > 0 ? fieldset.find('.module') : fieldset.children();
                        tabContent.append(content);
                        fieldset.hide(); // Hide original fieldset
                    });

                    tabContents.append(tabContent);
                }
            });

            // Insert tabs before the first multilingual fieldset
            var firstLangFieldset = langFieldsets.first();
            tabsContainer.append(tabHeaders);
            tabsContainer.append(tabContents);
            firstLangFieldset.before(tabsContainer);

            // Add click handlers
            $('.lang-tab-header').click(function () {
                var selectedLang = $(this).data('lang');
                switchToTab(selectedLang);
                saveSelectedTab(selectedLang);
            });

            // Show the previously selected tab or default to English
            var selectedTab = getSelectedTab();
            if ($('.lang-tab-header[data-lang="' + selectedTab + '"]').length === 0) {
                selectedTab = 'en'; // Fallback to English
            }
            switchToTab(selectedTab);
        }

        function switchToTab(langCode) {
            // Remove active class from all tabs
            $('.lang-tab-header').removeClass('active');
            $('.lang-tab-content').removeClass('active');

            // Add active class to selected tab
            $('.lang-tab-header[data-lang="' + langCode + '"]').addClass('active');
            $('.lang-tab-content[data-lang="' + langCode + '"]').addClass('active');
        }

        // Handle form validation - show tab with errors
        function showTabWithErrors() {
            $('.lang-tab-content').each(function () {
                var tabContent = $(this);
                if (tabContent.find('.errorlist').length > 0 || tabContent.find('.error').length > 0) {
                    var langCode = tabContent.data('lang');
                    switchToTab(langCode);
                    return false; // Break loop
                }
            });
        }

        // Check for errors on page load
        setTimeout(showTabWithErrors, 100);

        // Keyboard shortcuts
        $(document).keydown(function (e) {
            if (e.ctrlKey || e.metaKey) {
                switch (e.which) {
                    case 49:
                        e.preventDefault();
                        switchToTab('en');
                        break;
                    case 50:
                        e.preventDefault();
                        switchToTab('mk');
                        break;
                }
            }
        });

        // Add keyboard shortcut hints
        if ($('.lang-tab-header').length > 0) {
            $('.lang-tab-header[data-lang="en"]').attr('title', 'English (Ctrl+1)');
            $('.lang-tab-header[data-lang="mk"]').attr('title', 'Македонски (Ctrl+2)');
        }
    });
})(django.jQuery);