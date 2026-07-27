var ClassTemplate = {
    Status: 1, //Opened
    Session: 2, //Regualr class academic
    Class: 3, //discussion - 233
    Dates: 4, //meeting date
    Times: 5, //monday tuesday12am 3am
    Rooms: 6,
    Instructors: 7,
    Seats: 8
}

var TimeCycle = {
    MONDAY: 0,
    TUESDAY: 24 * 60 * 1,
    WEDNESDAY: 24 * 60 * 2,
    THURSDAY: 24 * 60 * 3,
    FRIDAY: 24 * 60 * 4,
    SATURDAY: 24 * 60 * 5,
    SUNDAY: 24 * 60 * 6
}


var AllClassInfos = []

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function firstClassesLoaded() {
    var Options =  document.getElementsByClassName("ps_grid-row  psc_disabled psc_rowact psc_disabled")
    while (Options.length <= 0) {
        await sleep(500)
    }
}

async function load(){
    var MoreButton = document.getElementById("SSR_CLSRCH_F_WK_SSR_CHANGE_BTN")
    while (MoreButton != null) {
        MoreButton.click()
        MoreButton = document.getElementById("SSR_CLSRCH_F_WK_SSR_CHANGE_BTN")
        await sleep(500)
    }
}
//Open Seats 15 of 504
//Waitlist Available Places 997 of 999

function get_waitlist(s){
    isWait = s.match("Open") == null

    if (isWait){
        numString = s.match(/\d+/g)
        return parseInt(numString[1]) - parseInt(numString[0]) + 1
    }else{
        return 0
    }
}
function get_min_time(s){
    var mins = 0
    timehours = s.match(/(\d+):/)[1]
    timemins = s.match(/:(\d+)/)[1]
    var Midday = s.match(/AM|PM/)[0]
    if (Midday == "AM" && timehours == "12")
        timehours = "0"
    if (Midday == "PM" && timehours != "12"){
        mins += 12 * 60
    }
        
    return mins + parseInt(timehours) * 60 + parseInt(timemins)
}
function timeConverter(s){
    timeRanges = []
    s = s.toUpperCase()
    DayPattern = /(SUNDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY)/g
    
    TimePattern = /\d+:\d+(?:AM|PM)/g
    Days = s.match(DayPattern)
    Time = s.match(TimePattern)
    if (Days == null)
        return [[0,0]]
    for(let i = 0; i < Days.length; i++){
      var StartTime = get_min_time(Time[0])
      var EndTime = get_min_time(Time[1])
      var DayMinute = TimeCycle[Days[i]]

      timeRanges.push([
        DayMinute + StartTime,
        DayMinute + EndTime
      ])
    }
        
    return timeRanges
}

async function main() {
    await firstClassesLoaded()
    await load()

    var Options =  document.getElementsByClassName("ps_grid-row  psc_disabled psc_rowact psc_disabled")

    for(let i = 0; i < Options.length; i++) {
        ClassInfo = {}
        for (const [key, value] of Object.entries(ClassTemplate)) {
            var Spans = Options[i].getElementsByClassName("ps_grid-cell")[value].querySelectorAll("span")
            var KeyOptions = []
            for(let j = 0; j < Spans.length; j++){
                KeyOptions[j] = Spans[j].textContent
            }
            
            if (key == "Times") {
                var OtherOptions = []
                
                for(let i = 0; i < KeyOptions.length; i++) {
                    OtherOptions[i] = timeConverter(KeyOptions[i])
                    KeyOptions[i] = KeyOptions[i].replace(/([A-Za-z])(\d)/g, "$1\n$2");
                }
                ClassInfo["TimeRanges"] = OtherOptions
            } else if(key == "Class"){
                var OtherOptions = []
                
                for(let i = 0; i < KeyOptions.length; i++) {
                    OtherOptions[i] = KeyOptions[i].match(/\d+/g)[0]
                }
                ClassInfo["ClassIds"] = OtherOptions
            } else if(key == "Seats"){
                var waitlist = 0
                for(let i = 0; i < KeyOptions.length; i++) {
                    waitlist = Math.max(get_waitlist(KeyOptions[i]), waitlist)
                }
                ClassInfo["Waitlist"] = waitlist
            }
            
            ClassInfo[key] = KeyOptions
        }
        AllClassInfos.push(ClassInfo)
    }
    return AllClassInfos
}

main()
