
function AnalysisTree() {
    $('.AnalysisTree').each(function () {
        let t = $(this);
        let name = t.attr('saucery-tree-name');
        let json = t.attr('saucery-tree-json');
        let parent = t;
        if (name) {
            let ul = $('<ul>').appendTo(t);
            let li = $('<li>').appendTo(ul);
            $('<a>').text(name).appendTo(li);
            parent = li;
        }

        $.getJSON(json, {format: 'raw'}, (data => PopulateAnalysisTree(t, parent, data)));
    });
}

function PopulateAnalysisTree(tree, parent, data) {
    let levelmap = new Map();

    data.forEach((conclusion) => {
        if (!conclusion.abnormal)
            return;
        let level = conclusion.level;
        if (!levelmap.has(level))
            levelmap.set(level, new Array());
        levelmap.get(level).push(conclusion);
    });

    ['critical', 'error', 'warning', 'info'].forEach((level) => {
        if (!levelmap.has(level))
            return;
        let ul = $('<ul>').appendTo(parent);
        let li = $('<li>').appendTo(ul);
        let entries = levelmap.get(level);
        let a = $('<a>').text(level + ' (' + entries.length + ')').appendTo(li);
        PopulateConclusions(li, entries);
    });

    tree.jstree({
        'core': {
            'themes': {
                'icons': false,
            },
        },
    });
}

function PopulateConclusions(parent, conclusions) {
    let parentul = $('<ul>').appendTo(parent);

    conclusions.forEach((conclusion) => {
        let li = $('<li>').text(conclusion.summary).appendTo(parentul);
        let ul = $('<ul>').appendTo(li);

        li = $('<li>').text(conclusion.description).appendTo(ul);
        ul = $('<ul>').appendTo(li);

        conclusion.details.forEach((detail) => {
            $('<li>').append(DetailAnchors(detail)).appendTo(ul);
        });
    });
}

function DetailAnchors(detail) {
    let div = $('<div>');
    const pattern = /([^{}]*)(?:\{(\w+)\})?/g;
    let matches = detail.description.matchAll(pattern);

    for (const match of matches) {
        if (match[1])
            $('<a>').text(match[1]).appendTo(div);
        if (match[2])
            DetailHrefAnchor(detail[match[2]]).appendTo(div);
    };

    return div;
}

function DetailHrefAnchor(entry) {
    let href = SauceryServicePathRoot + entry.path + '#LINE' + entry.first_line;

    return $('<a>').text(entry.text).attr({'href': href, 'target': '_blank'});
}
