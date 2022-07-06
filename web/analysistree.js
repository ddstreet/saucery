
function AnalysisTree() {
    $('.AnalysisTree').each(function () {
        let t = $(this);
        let name = t.attr('saucery-tree-name');
        let json = t.attr('saucery-tree-json');
        if (!name || !json)
            return;

        $('<h3>').text(name).appendTo(t);
        parent = $('<div>').appendTo(t);
        CreateAccordion(t);

        $.getJSON(json, {format: 'raw'}, (data => PopulateAnalysisTree(parent, data)));
    });
}

function CreateAccordion(element, active=false) {
    element.accordion({
        active: active,
        collapsible: true,
        heightStyle: 'content',
    });
}

function PopulateAnalysisTree(parent, data) {
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
        let entries = levelmap.get(level);
        let leveltree = $('<div>').appendTo(parent);
        $('<h3>').text(level + ' (' + entries.length + ')').appendTo(leveltree);
        PopulateConclusions($('<div>').appendTo(leveltree), entries);
        CreateAccordion(leveltree);
    });
}

function PopulateConclusions(parent, conclusions) {
    conclusions.forEach((conclusion) => {
        PopulateConclusion(parent, conclusion);
    });
    CreateAccordion(parent);
}

function PopulateConclusion(parent, conclusion) {
    $('<h3>').text(conclusion.summary).appendTo(parent);
    PopulateConclusionDetail($('<div>').appendTo(parent), conclusion);
}

function PopulateConclusionDetail(parent, conclusion) {
    if (conclusion.description) {
        let div = $('<div>').addClass('ConclusionDescription').appendTo(parent);
        $('<a>').text(conclusion.description).appendTo(div);
    }

    conclusion.details.forEach((detail, index) => {
        DetailAnchors(detail, index + 1).appendTo(parent);
    });
}

function DetailAnchors(detail, index) {
    let div = $('<div>');
    const pattern = /([^{}]*)(?:\{(\w+)\})?/g;
    let matches = detail.description.matchAll(pattern);

    $('<a>').text(index + ': ').addClass('ConclusionDetailIndex').appendTo(div);

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
